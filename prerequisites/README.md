## Pre-requisites
The Amazon Bedrock Knowledge Base created by this code is used as the RAG vector database for the RAG-based AI chat application.

This Python script performs the following steps:

1. Creates an S3 bucket for storing documents
2. Uploads PDF files from the specified directory to S3
3. Creates necessary IAM roles and policies for Bedrock to access resources
4. Sets up an OpenSearch Serverless collection for vector storage
5. Creates an OpenSearch Serverless (AOSS) policy for Bedrock execution role
6. Creates an index with vector search capabilities
7. Creates a Bedrock Knowledge Base with the appropriate configurations
8. Creates a data source pointing to the S3 bucket
9. Starts a data ingestion job to process the documents
10. Performs a test query to verify the setup

To use this code:

1. Ensure you have AWS credentials configured with appropriate permissions
```bash
aws configure
```

2. Install required dependencies:
```bash
pip install -r requirements.txt
```
3. Run the script
```bash
python create_bedrock_kb.py
```

4. Copy the Knowledge Base ID output (alternatively, you can also get the ID from Bedrock console web page)

### Acknowledgment
- This code is sampled from [Amazon Bedrock Workshop - Module 2 - Knowledge Bases and RAG](https://github.com/aws-samples/amazon-bedrock-workshop/tree/75aa73f60903f85bd0c7abc84fa6ff85c0789105/02_Knowledge_Bases_and_RAG) with slight modifications.
- The data used for the knowledge base is retrieved from [JPMorgan Chase Investor Relations | Annual Report & Proxy site](https://www.jpmorganchase.com/ir/annual-report)