# scripts/init-aws.sh - Initialize LocalStack resources
#!/bin/bash
set -e

echo "Initializing LocalStack AWS resources..."

# Create SQS queues
awslocal sqs create-queue --queue-name contract-download-queue
awslocal sqs create-queue --queue-name contract-download-queue-dlq
awslocal sqs create-queue --queue-name document-parse-queue
awslocal sqs create-queue --queue-name document-parse-queue-dlq
awslocal sqs create-queue --queue-name validation-complete-queue

# Create S3 bucket
awslocal s3 mb s3://forth-contracts

# Set bucket policy for local access
awslocal s3api put-bucket-policy --bucket forth-contracts --policy '{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::forth-contracts",
        "arn:aws:s3:::forth-contracts/*"
      ]
    }
  ]
}'

echo "LocalStack initialization complete!"