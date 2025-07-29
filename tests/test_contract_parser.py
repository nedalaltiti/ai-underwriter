# tests/unit/test_contract_parser.py
import pytest
from unittest.mock import Mock, AsyncMock
from datetime import date

from contract_parser.core.parser import ContractParser
from contract_parser.models.entities import (
    ContractEntities, ClientInfo, FinancialInfo, DebtInfo
)
from contract_parser.config import ParserConfig


@pytest.mark.asyncio
class TestContractParser:
    """Test contract parser functionality."""
    
    async def test_parse_contract_success(self, mock_llm_provider):
        """Test successful contract parsing."""
        # Setup
        config = ParserConfig(service_name="test-parser")
        
        mock_database = AsyncMock()
        mock_database.create_contract.return_value = "test-contract-id"
        
        # Mock document loader
        mock_document = Mock()
        mock_document.get_text.return_value = "Sample contract text"
        mock_document.metadata = {"contract_date": date.today()}
        
        parser = ContractParser(config, mock_llm_provider, mock_database)
        parser.document_loader = AsyncMock()
        parser.document_loader.load_from_s3.return_value = mock_document
        
        # Mock extraction service
        mock_entities = ContractEntities(
            client_info=ClientInfo(
                name="John Doe",
                ssn_last_four="1234",
                state="CA"
            ),
            financial_info=FinancialInfo(
                total_debt=25000.0,
                monthly_payment=500.0,
                program_length_months=48,
                enrolled_debts=[
                    DebtInfo(
                        creditor_name="Chase",
                        balance=10000.0,
                        debt_type="credit_card"
                    )
                ]
            )
        )
        parser.extraction_service = AsyncMock()
        parser.extraction_service.extract_entities.return_value = mock_entities
        
        # Mock validation service
        from contract_parser.models.entities import ValidationResult
        mock_validations = [
            ValidationResult(
                validation_type="hardship_claim",
                is_valid=True,
                message="Valid hardship"
            ),
            ValidationResult(
                validation_type="payment_terms",
                is_valid=True,
                message="Valid payment terms"
            )
        ]
        parser.validation_service = AsyncMock()
        parser.validation_service.validate_contract.return_value = mock_validations
        
        # Execute
        result = await parser.parse_contract(
            contact_id="12345",
            doc_id="67890",
            s3_key="contracts/2024/01/01/12345/67890/test.pdf"
        )
        
        # Assert
        assert result["contract_id"] == "test-contract-id"
        assert result["status"] == "completed"
        assert len(result["entities"]) > 0
        assert len(result["validations"]) == 2
        assert all(v["is_valid"] for v in result["validations"])
        
        # Verify database calls
        mock_database.create_contract.assert_called_once()
        mock_database.update_contract.assert_called_with(
            "test-contract-id",
            status="completed"
        )
    
    async def test_parse_contract_validation_failure(self, mock_llm_provider):
        """Test contract parsing with validation failures."""
        config = ParserConfig(service_name="test-parser")
        
        mock_database = AsyncMock()
        mock_database.create_contract.return_value = "test-contract-id"
        
        parser = ContractParser(config, mock_llm_provider, mock_database)
        
        # Setup mocks
        parser.document_loader = AsyncMock()
        parser.document_loader.load_from_s3.return_value = Mock(
            get_text=Mock(return_value="Contract text"),
            metadata={}
        )
        
        parser.extraction_service = AsyncMock()
        parser.extraction_service.extract_entities.return_value = ContractEntities()
        
        # Mock validation failures
        from contract_parser.models.entities import ValidationResult
        parser.validation_service = AsyncMock()
        parser.validation_service.validate_contract.return_value = [
            ValidationResult(
                validation_type="payment_terms",
                is_valid=False,
                message="Monthly payment below minimum"
            )
        ]
        
        result = await parser.parse_contract(
            contact_id="12345",
            doc_id="67890",
            s3_key="test.pdf"
        )
        
        assert result["status"] == "validation_failed"
        assert any(not v["is_valid"] for v in result["validations"])
