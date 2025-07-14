# scripts/setup_aws_resources.sh - Setup AWS resources

#!/bin/bash
set -euo pipefail

ENVIRONMENT=${1:-staging}
REGION=${AWS_REGION:-us-west-1}

log_info() {
    echo "[INFO] $1"
}

# Create S3 bucket
create_s3_bucket() {
    local bucket_name="forth-contracts-${ENVIRONMENT}"
    
    log_info "Creating S3 bucket: $bucket_name"
    
    if aws s3api head-bucket --bucket "$bucket_name" 2>/dev/null; then
        log_info "Bucket already exists"
    else
        aws s3api create-bucket \
            --bucket "$bucket_name" \
            --region "$REGION" \
            --create-bucket-configuration LocationConstraint="$REGION"
        
        # Enable versioning
        aws s3api put-bucket-versioning \
            --bucket "$bucket_name" \
            --versioning-configuration Status=Enabled
        
        # Enable encryption
        aws s3api put-bucket-encryption \
            --bucket "$bucket_name" \
            --server-side-encryption-configuration '{
                "Rules": [{
                    "ApplyServerSideEncryptionByDefault": {
                        "SSEAlgorithm": "AES256"
                    }
                }]
            }'
        
        # Set lifecycle policy
        aws s3api put-bucket-lifecycle-configuration \
            --bucket "$bucket_name" \
            --lifecycle-configuration '{
                "Rules": [{
                    "ID": "DeleteOldVersions",
                    "Status": "Enabled",
                    "NoncurrentVersionExpiration": {
                        "NoncurrentDays": 90
                    }
                }]
            }'
    fi
}

# Create SQS queues
create_sqs_queues() {
    local queues=(
        "contract-download-queue"
        "document-parse-queue"
        "validation-complete-queue"
    )
    
    for queue in "${queues[@]}"; do
        local queue_name="${queue}-${ENVIRONMENT}"
        local dlq_name="${queue}-dlq-${ENVIRONMENT}"
        
        log_info "Creating SQS queue: $queue_name"
        
        # Create DLQ first
        DLQ_URL=$(aws sqs create-queue \
            --queue-name "$dlq_name" \
            --attributes '{
                "MessageRetentionPeriod": "1209600",
                "VisibilityTimeout": "300"
            }' \
            --query 'QueueUrl' \
            --output text)
        
        # Get DLQ ARN
        DLQ_ARN=$(aws sqs get-queue-attributes \
            --queue-url "$DLQ_URL" \
            --attribute-names QueueArn \
            --query 'Attributes.QueueArn' \
            --output text)
        
        # Create main queue with DLQ
        aws sqs create-queue \
            --queue-name "$queue_name" \
            --attributes "{
                \"MessageRetentionPeriod\": \"345600\",
                \"VisibilityTimeout\": \"300\",
                \"RedrivePolicy\": \"{\\\"deadLetterTargetArn\\\":\\\"${DLQ_ARN}\\\",\\\"maxReceiveCount\\\":3}\"
            }"
    done
}

# Create RDS instance
create_rds_instance() {
    local db_instance="forth-contracts-${ENVIRONMENT}"
    
    log_info "Creating RDS PostgreSQL instance: $db_instance"
    
    # Check if instance exists
    if aws rds describe-db-instances --db-instance-identifier "$db_instance" 2>/dev/null; then
        log_info "RDS instance already exists"
    else
        aws rds create-db-instance \
            --db-instance-identifier "$db_instance" \
            --db-instance-class "db.t3.medium" \
            --engine "postgres" \
            --engine-version "15.4" \
            --master-username "forth_admin" \
            --master-user-password "${DB_PASSWORD}" \
            --allocated-storage 100 \
            --storage-encrypted \
            --backup-retention-period 7 \
            --preferred-backup-window "03:00-04:00" \
            --preferred-maintenance-window "sun:04:00-sun:05:00" \
            --vpc-security-group-ids "${DB_SECURITY_GROUP}" \
            --db-subnet-group-name "forth-db-subnet-group" \
            --tags "Key=Environment,Value=${ENVIRONMENT}" "Key=Service,Value=forth-ai-underwriting"
    fi
}

# Create IAM roles
create_iam_roles() {
    local services=("webhook-ingestion" "document-downloader" "contract-parser")
    
    for service in "${services[@]}"; do
        local role_name="forth-${service}-${ENVIRONMENT}-role"
        
        log_info "Creating IAM role: $role_name"
        
        # Create role
        aws iam create-role \
            --role-name "$role_name" \
            --assume-role-policy-document '{
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "eks.amazonaws.com"
                    },
                    "Action": "sts:AssumeRole"
                }]
            }' || true
        
        # Attach policies based on service
        case $service in
            "webhook-ingestion")
                aws iam attach-role-policy \
                    --role-name "$role_name" \
                    --policy-arn "arn:aws:iam::aws:policy/AmazonSQSFullAccess"
                ;;
            "document-downloader")
                aws iam attach-role-policy \
                    --role-name "$role_name" \
                    --policy-arn "arn:aws:iam::aws:policy/AmazonS3FullAccess"
                aws iam attach-role-policy \
                    --role-name "$role_name" \
                    --policy-arn "arn:aws:iam::aws:policy/AmazonSQSFullAccess"
                ;;
            "contract-parser")
                aws iam attach-role-policy \
                    --role-name "$role_name" \
                    --policy-arn "arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess"
                aws iam attach-role-policy \
                    --role-name "$role_name" \
                    --policy-arn "arn:aws:iam::aws:policy/AmazonSQSFullAccess"
                ;;
        esac
    done
}

# Main
main() {
    log_info "Setting up AWS resources for environment: $ENVIRONMENT"
    
    create_s3_bucket
    create_sqs_queues
    create_rds_instance
    create_iam_roles
    
    log_info "AWS resources setup completed!"
}

main
