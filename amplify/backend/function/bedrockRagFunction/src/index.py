import json
import os
import boto3

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

def handler(event, context):
    try:
        print('received event:')
        print(event)

        # Get current AWS region
        aws_region = os.environ['AWS_REGION']

        # Get AWS account ID
        sts = boto3.client('sts')
        account_id = sts.get_caller_identity()['Account']

        # Create Bedrock Agent runtime client
        bedrock_agent_runtime = boto3.client(
            service_name='bedrock-agent-runtime',
            region_name=aws_region
        )

        # Parse request body
        body = json.loads(event['body'])
        query = body.get('query', '')
        print(f"user query: {query}")        
        
        # Query the Bedrock with Knowledge Base
        # Replace the knowledgeBaseId with the Knowledge Base ID from the prerequisite script
        # You can also change the FM. Refer to AWS documentation which models are supported          
        response = bedrock_agent_runtime.retrieve_and_generate(
            input={
                'text': query
            },
            retrieveAndGenerateConfiguration={
                'type': 'KNOWLEDGE_BASE',
                'knowledgeBaseConfiguration': {
                    'knowledgeBaseId': "<provide the knowledge base ID from prerequisite script>",
                    'modelArn': f"arn:aws:bedrock:{aws_region}:{account_id}:inference-profile/us.anthropic.claude-3-7-sonnet-20250219-v1:0"
                }
            }
        )

        citations = citation_s3_uris(response["citations"])
        response_body = {
            'text': response['output']['text'],
            'citations': citations
        }

        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Headers': '*',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'OPTIONS,POST,GET'
            },
            'body': json.dumps(response_body)
        }
    except Exception as e:
        print(f'Error: {str(e)}')
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': '*'
            },
            'body': json.dumps({'error': str(e)})
        }