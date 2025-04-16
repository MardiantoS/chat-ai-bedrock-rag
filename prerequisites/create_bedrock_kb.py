import boto3
import json
import time
import random
from pathlib import Path

# Use the AWS SDK for OpenSearch
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

def create_bedrock_knowledge_base(region_name=None, data_dir='data'):
    """
    Create a Bedrock Knowledge Base with data from a local directory.
    
    Args:
        region_name: AWS region (defaults to session region if None)
        data_dir: Local directory containing the data files
    
    Returns:
        dict: Information about the created knowledge base
    """
    # Create boto3 session and set region
    boto_session = boto3.Session(region_name=region_name)
    aws_region = boto_session.region_name

    # Create boto3 clients
    aoss_client = boto_session.client('opensearchserverless')
    bedrock_agent_client = boto_session.client('bedrock-agent')
    s3_client = boto_session.client('s3')
    sts_client = boto_session.client('sts')

    # Generate unique identifiers for resources
    resource_suffix = random.randrange(100, 999)
    s3_bucket_name = f"chat-ai-bedrock-kb-{resource_suffix}"
    aoss_collection_name = f"bedrock-kb-collection-{resource_suffix}"
    aoss_index_name = f"bedrock-kb-index-{resource_suffix}"
    bedrock_kb_name = f"bedrock-kb-{resource_suffix}"

    # Set embedding model
    embedding_model_id = 'amazon.titan-embed-text-v2:0' # Change this to your preferred embedding model
    embedding_model_arn = f"arn:aws:bedrock:{aws_region}::foundation-model/{embedding_model_id}"
    embedding_model_dim = 1024

    # Step 1: Create S3 bucket for KB data source
    try:
        if aws_region == "us-east-1":
            s3_client.create_bucket(Bucket=s3_bucket_name)
        else:
            s3_client.create_bucket(
                Bucket=s3_bucket_name,
                CreateBucketConfiguration={ "LocationConstraint": aws_region }
            )
    except s3_client.exceptions.BucketAlreadyExists:
        print(f"Bucket {s3_bucket_name} already exists.")

    # Step 2: Upload data files
    data_path = Path(data_dir)
    print(f"Uploading files from {data_path} to S3...")
    for file_path in data_path.glob("**/*.pdf"):
        s3_key = file_path.name
        s3_client.upload_file(str(file_path), s3_bucket_name, s3_key)
        print(f"Uploaded: {file_path.name} to s3://{s3_bucket_name}/{s3_key}")

    # Step 3: Create IAM role for Bedrock KB
    print("Creating Bedrock execution role...")
    account_id = sts_client.get_caller_identity()["Account"]
    iam_client = boto_session.client('iam')

    # Define policy documents with least privilege permission
    foundation_model_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": ["bedrock:InvokeModel"],
            "Resource": [
                f"arn:aws:bedrock:{aws_region}::foundation-model/amazon.titan-embed-text-v1",
                f"arn:aws:bedrock:{aws_region}::foundation-model/amazon.titan-embed-text-v2:0"
            ]
        }]
    }

    s3_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": ["s3:GetObject", "s3:ListBucket"],
            "Resource": [
                f"arn:aws:s3:::{s3_bucket_name}",
                f"arn:aws:s3:::{s3_bucket_name}/*"
            ],
            "Condition": {
                "StringEquals": {
                    "aws:ResourceAccount": account_id
                }
            }
        }]
    }

    assume_role_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "bedrock.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }]
    }

    # Create policies and role
    role_name = f"BedrockKBRole-{resource_suffix}"
    fm_policy_name = f"BedrockFMPolicy-{resource_suffix}"
    s3_policy_name = f"BedrockS3Policy-{resource_suffix}"

    fm_policy = iam_client.create_policy(
        PolicyName=fm_policy_name,
        PolicyDocument=json.dumps(foundation_model_policy),
        Description='Policy for accessing foundation model'
    )

    s3_policy = iam_client.create_policy(
        PolicyName=s3_policy_name,
        PolicyDocument=json.dumps(s3_policy),
        Description='Policy for reading documents from s3'
    )

    kb_execution_role = iam_client.create_role(
        RoleName=role_name,
        AssumeRolePolicyDocument=json.dumps(assume_role_policy),
        Description='Amazon Bedrock Knowledge Base Execution Role for accessing OSS and S3',
        MaxSessionDuration=3600        
    )

    # Attach policies to role
    iam_client.attach_role_policy(
        RoleName=role_name,
        PolicyArn=fm_policy['Policy']['Arn']
    )

    iam_client.attach_role_policy(
        RoleName=role_name,
        PolicyArn=s3_policy['Policy']['Arn']
    )

    # Get role ARN
    role_arn = kb_execution_role['Role']['Arn']
    print(f"Created role with ARN: {role_arn}")

    # Step 4: Create OpenSearch Serverless collection
    print(f"Creating AOSS collection: {aoss_collection_name}...")

    # Create security policies
    encryption_policy_name = f"bedrock-enc-{resource_suffix}"
    network_policy_name = f"bedrock-net-{resource_suffix}"
    access_policy_name = f"bedrock-access-{resource_suffix}"

    aoss_client.create_security_policy(
        name=encryption_policy_name,
        policy=json.dumps({
            'Rules': [{'Resource': ['collection/' + aoss_collection_name],
                      'ResourceType': 'collection'}],
            'AWSOwnedKey': True
        }),
        type='encryption'
    )

    aoss_client.create_security_policy(
        name=network_policy_name,
        policy=json.dumps([{
            'Rules': [{'Resource': ['collection/' + aoss_collection_name],
                      'ResourceType': 'collection'}],
            'AllowFromPublic': True
        }]),
        type='network'
    )

    # Get current user ARN
    user_arn = sts_client.get_caller_identity()['Arn']

    aoss_client.create_access_policy(
        name=access_policy_name,
        policy=json.dumps([{
            'Rules': [
                {
                    'Resource': ['collection/' + aoss_collection_name],
                    'Permission': [
                        'aoss:CreateCollectionItems',
                        'aoss:DeleteCollectionItems',
                        'aoss:UpdateCollectionItems',
                        'aoss:DescribeCollectionItems'
                    ],
                    'ResourceType': 'collection'
                },
                {
                    'Resource': ['index/' + aoss_collection_name + '/*'],
                    'Permission': [
                        'aoss:CreateIndex',
                        'aoss:DeleteIndex',
                        'aoss:UpdateIndex',
                        'aoss:DescribeIndex',
                        'aoss:ReadDocument',
                        'aoss:WriteDocument'
                    ],
                    'ResourceType': 'index'
                }
            ],
            'Principal': [user_arn, role_arn],
            'Description': 'Access policy for Bedrock KB'
        }]),
        type='data'
    )

    # Create AOSS collection
    aoss_collection = aoss_client.create_collection(
        name=aoss_collection_name,
        type='VECTORSEARCH'
    )

    # Wait for collection to become active
    print("Waiting for AOSS collection to become active...", end='')
    while True:
        response = aoss_client.list_collections(
            collectionFilters={'name': aoss_collection_name}
        )
        status = response['collectionSummaries'][0]['status']
        if status in ('ACTIVE', 'FAILED'):
            print(" done.")
            collection_id = response['collectionSummaries'][0]['id']
            collection_arn = response['collectionSummaries'][0]['arn']
            break
        print('█', end='', flush=True)
        time.sleep(5)

    # Step 5: Create AOSS policy for Bedrock execution role
    oss_policy_name = f'BedrockOSSPolicy-{resource_suffix}'
    oss_policy = iam_client.create_policy(
        PolicyName=oss_policy_name,
        PolicyDocument=json.dumps({
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Action": ["aoss:APIAccessAll"],
                "Resource": [f"arn:aws:aoss:{aws_region}:{account_id}:collection/{collection_id}"]
            }]
        }),
        Description='Policy for accessing opensearch serverless'
    )

    iam_client.attach_role_policy(
        RoleName=role_name,
        PolicyArn=oss_policy['Policy']['Arn']
    )

    # Give time for policies to propagate
    print("Waiting 60 sec for data access rules to be enforced: ", end='')
    for _ in range(12):  # 12 * 5 sec = 60 sec
        print('█', end='', flush=True)
        time.sleep(5)
    print(" done.")

    print("Created and attached policy with ARN:", oss_policy['Policy']['Arn'])

    # Auth credentials
    credentials = boto_session.get_credentials()
    awsauth = AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        aws_region,
        'aoss',
        session_token=credentials.token
    )

    # Connect to OpenSearch
    host = f"{collection_id}.{aws_region}.aoss.amazonaws.com"
    os_client = OpenSearch(
        hosts=[{'host': host, 'port': 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=300
    )

    # Create index with vector search capabilities
    index_definition = {
        "settings": {
            "index.knn": "true",
            "number_of_shards": 1,
            "knn.algo_param.ef_search": 512,
            "number_of_replicas": 0,
        },
        "mappings": {
            "properties": {
                "vector": {
                    "type": "knn_vector",
                    "dimension": embedding_model_dim,
                    "method": {
                        "name": "hnsw",
                        "engine": "faiss",
                        "space_type": "l2"
                    },
                },
                "text": {
                    "type": "text"
                },
                "text-metadata": {
                    "type": "text"
                }
            }
        }
    }

    os_client.indices.create(index=aoss_index_name, body=index_definition)
    
    # Wait for index creation to propagate
    print("Waiting for index to be ready...")
    for _ in range(6):  # 6 * 5 sec = 30 sec
        print('█', end='', flush=True)
        time.sleep(5)
    print(" done.")

    # Step 7: Create Bedrock Knowledge Base (built-in RAG capability)
    print(f"Creating Bedrock Knowledge Base: {bedrock_kb_name}...")
    
    # Storage configuration
    storage_config = {
        "type": "OPENSEARCH_SERVERLESS",
        "opensearchServerlessConfiguration": {
            "collectionArn": collection_arn,
            "vectorIndexName": aoss_index_name,
            "fieldMapping": {
                "vectorField": "vector",
                "textField": "text",
                "metadataField": "text-metadata"
            }
        }
    }

    # KB configuration
    knowledge_base_config = {
        "type": "VECTOR",
        "vectorKnowledgeBaseConfiguration": {
            "embeddingModelArn": embedding_model_arn
        }
    }
    
    # Create KB
    kb_response = bedrock_agent_client.create_knowledge_base(
        name=bedrock_kb_name,
        description="Chat AI with Bedrock Document knowledge base",
        roleArn=role_arn,
        knowledgeBaseConfiguration=knowledge_base_config,
        storageConfiguration=storage_config
    )

    kb_id = kb_response['knowledgeBase']['knowledgeBaseId']
    
    # Wait for KB to become active
    print("Waiting for Knowledge Base to become active...", end='')
    while True:
        response = bedrock_agent_client.get_knowledge_base(knowledgeBaseId=kb_id)
        if response['knowledgeBase']['status'] == 'ACTIVE':
            print(" done.")
            break

        print('█', end='', flush=True)
        time.sleep(5)
    
    # Step 8: Create data source and ingest data
    print("Creating data source...")
    
    # Data source configuration
    data_source_config = {
        "type": "S3",
        "s3Configuration": {
            "bucketArn": f"arn:aws:s3:::{s3_bucket_name}"
        }
    }

    # Vector ingestion configuration
    vector_ingestion_config = {
        "chunkingConfiguration": {
            "chunkingStrategy": "FIXED_SIZE",
            "fixedSizeChunkingConfiguration": {
                "maxTokens": 512,
                "overlapPercentage": 20
            }
        }
    }

    # Create data source
    ds_response = bedrock_agent_client.create_data_source(
        name=bedrock_kb_name,
        description="Document data source",
        knowledgeBaseId=kb_id,
        dataSourceConfiguration=data_source_config,
        vectorIngestionConfiguration=vector_ingestion_config
    )
    
    ds_id = ds_response['dataSource']['dataSourceId']
    
    # Step 9: Start ingestion job
    print("Starting ingestion job...")
    job_response = bedrock_agent_client.start_ingestion_job(
        knowledgeBaseId=kb_id,
        dataSourceId=ds_id
    )
    
    job_id = job_response['ingestionJob']['ingestionJobId']

    # Wait for ingestion to complete
    print("Waiting for ingestion job to complete...", end='')
    while True:
        response = bedrock_agent_client.get_ingestion_job(
            knowledgeBaseId=kb_id,
            dataSourceId=ds_id,
            ingestionJobId=job_id
        )
        if response['ingestionJob']['status'] == 'COMPLETE':
            print(" done.")
            break

        print('█', end='', flush=True)
        time.sleep(10)

    # Return KB information
    kb_info = {
        "kb_id": kb_id,
        "kb_name": bedrock_kb_name,
        "region": aws_region,
        "account_id": account_id,
        "s3_bucket": s3_bucket_name,
        "aoss_collection": aoss_collection_name,
        "aoss_index": aoss_index_name,
        "data_source_id": ds_id
    }
    
    print("Knowledge Base created successfully!")
    print(f"KB ID: {kb_id}")
    print(f"S3 Bucket: {s3_bucket_name}")
    
    return kb_info

# Call this function if you'd like to check which FMs are available in your account
def list_available_models():
    bedrock = boto3.client('bedrock')
    response = bedrock.list_foundation_models()
    models = response['modelSummaries']

    for model in models:
        print(f"Model ID: {model['modelId']}")
        print(f"Model ARN: {model.get('modelArn', 'ARN not available')}")
        print(f"Provider: {model['providerName']}")
        print(f"Model Name: {model['modelName']}")
        print("---")

def citation_s3_uris(citations):
    # Extract S3 location URIs
    s3_uris = []
    for item in citations:
        for reference in item.get('retrievedReferences', []):
            location = reference.get('location', {})
            if location.get('type') == 'S3':
                s3_location = location.get('s3Location', {})
                uri = s3_location.get('uri')
                if uri:
                    s3_uris.append(uri)

    return s3_uris

if __name__ == "__main__":
    # Create a Bedrock Knowledge Base with data in the 'data' directory
    kb_info = create_bedrock_knowledge_base(data_dir='data')
    
    # Step 10: Example query to test the KB
    bedrock_agent_runtime = boto3.client(service_name='bedrock-agent-runtime', region_name=kb_info['region'])
    
    test_query = "How much is the net income per share in 2023 and 2024?"
    
    # Example of a simple query using the knowledge base
    response = bedrock_agent_runtime.retrieve_and_generate(
        input={
            'text': test_query
        },
        retrieveAndGenerateConfiguration={
            'type': 'KNOWLEDGE_BASE',
            'knowledgeBaseConfiguration': {
                'knowledgeBaseId': kb_info['kb_id'],
                'modelArn': f"arn:aws:bedrock:{kb_info['region']}:{kb_info['account_id']}:inference-profile/us.anthropic.claude-3-7-sonnet-20250219-v1:0"
            }
        }
    )

    print("\nTest Query Result:")
    print(f"Query: {test_query}")
    print(f"Response: {response['output']['text']}\n")

    print("Source files:")
    print('\n'.join(citation_s3_uris(response["citations"])))

    print(f"\nKnowledge Base ID: {kb_info['kb_id']}")