# services/document-parser/src/core/validator.py
"""Underwriting validation logic for extracted documents."""

from typing import List, Set

from models.base import DebtType
from models.extraction import ExtractedDocument
from models.validation import ValidationResult
from utils.logging import get_logger

logger = get_logger(__name__)


class UnderwritingValidator:
    """Validate extracted documents against underwriting rules."""
    
    # State to company mapping
    STATE_COMPANY_MAP = {
        'AL': 'Company A', 'AK': 'Company A', 'AZ': 'Company B',
        'AR': 'Company B', 'CA': 'Company C', 'CO': 'Company C',
        'CT': 'Company A', 'DE': 'Company B', 'FL': 'Company C',
        'GA': 'Company A', 'HI': 'Company B', 'ID': 'Company C',
        'IL': 'Company A', 'IN': 'Company B', 'IA': 'Company C',
        'KS': 'Company A', 'KY': 'Company B', 'LA': 'Company C',
        'ME': 'Company A', 'MD': 'Company B', 'MA': 'Company C',
        'MI': 'Company A', 'MN': 'Company B', 'MS': 'Company C',
        'MO': 'Company A', 'MT': 'Company B', 'NE': 'Company C',
        'NV': 'Company A', 'NH': 'Company B', 'NJ': 'Company C',
        'NM': 'Company A', 'NY': 'Company B', 'NC': 'Company C',
        'ND': 'Company A', 'OH': 'Company B', 'OK': 'Company C',
        'OR': 'Company A', 'PA': 'Company B', 'RI': 'Company C',
        'SC': 'Company A', 'SD': 'Company B', 'TN': 'Company C',
        'TX': 'Company A', 'UT': 'Company B', 'VT': 'Company C',
        'VA': 'Company A', 'WA': 'Company B', 'WV': 'Company C',
        'WI': 'Company A', 'WY': 'Company B'
    }
    
    # High-risk creditors list
    HIGH_RISK_CREDITORS: Set[str] = {
        "1ST FRANKLIN", "CREST FINANCIAL", "KARROT LOANS", "RAND BRKS CU",
        "DIAMOND RESORTS", "LENDING USA", "RED RIVER CREDIT CORP",
        "PAYDAY LOANS", "CASH ADVANCE", "TITLE LOAN", "RENT A CENTER",
        "AARON'S", "PROGRESSIVE LEASING", "SNAP FINANCE", "KATAPULT",
        "ACIMA", "SMARTPAY LEASING", "TEMPOE", "FLEXSHOPPER"
    }
    
    # Excluded debt types
    EXCLUDED_DEBT_TYPES: Set[DebtType] = {
        # Add specific debt types that are excluded
    }
    
    def validate_document(self, doc: ExtractedDocument) -> List[ValidationResult]:
        """
        Run all validation checks on the document.
        
        Args:
            doc: Extracted document to validate
            
        Returns:
            List of validation results
        """
        logger.info(f"Starting validation for client: {doc.client_info.name}")
        results = []
        
        # 1. Financial validations
        results.extend(self._validate_financial_requirements(doc))
        
        # 2. Contract validations
        results.extend(self._validate_contract_requirements(doc))
        
        # 3. Debt composition validations
        results.extend(self._validate_debt_composition(doc))
        
        # 4. Program structure validations
        results.extend(self._validate_program_structure(doc))
        
        # 5. Compliance validations
        results.extend(self._validate_compliance_requirements(doc))
        
        # Update document with results
        doc.validation_results = results
        
        # Log summary
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        logger.info(f"Validation complete: {passed}/{total} checks passed")
        
        return results
    
    def _validate_financial_requirements(self, doc: ExtractedDocument) -> List[ValidationResult]:
        """Validate financial requirements."""
        results = []
        
        # Budget surplus validation
        surplus = doc.financial_analysis.net_income - doc.financial_analysis.monthly_program_deposit
        results.append(ValidationResult(
            field="budget_surplus",
            passed=surplus > 0,
            reason=f"Budget surplus: ${surplus:.2f}" if surplus > 0 else f"Budget deficit: ${abs(surplus):.2f}",
            severity="critical" if surplus <= 0 else "low",
            category="financial"
        ))
        
        # Minimum payment validation
        min_payment = doc.financial_analysis.monthly_program_deposit
        results.append(ValidationResult(
            field="minimum_payment",
            passed=min_payment >= 250,
            reason=f"Monthly payment: ${min_payment:.2f}",
            severity="high" if min_payment < 250 else "low",
            category="financial"
        ))
        
        # Debt-to-income ratio
        debt_to_income = (doc.financial_analysis.total_enrolled_debt / 
                         (doc.financial_analysis.monthly_income * 12)) * 100
        results.append(ValidationResult(
            field="debt_to_income_ratio",
            passed=debt_to_income <= 80,  # 80% max ratio
            reason=f"Debt-to-income ratio: {debt_to_income:.1f}%",
            severity="medium" if debt_to_income > 80 else "low",
            category="financial"
        ))
        
        return results
    
    def _validate_contract_requirements(self, doc: ExtractedDocument) -> List[ValidationResult]:
        """Validate contract-specific requirements."""
        results = []
        
        # IP addresses must be different
        results.append(ValidationResult(
            field="ip_addresses_different",
            passed=doc.sender_ip != doc.signer_ip,
            reason="Sender and signer IPs are different" if doc.sender_ip != doc.signer_ip 
                   else f"Same IP used: {doc.sender_ip}",
            severity="critical" if doc.sender_ip == doc.signer_ip else "low",
            category="legal"
        ))
        
        # First payment timing
        days_to_first = (doc.first_payment_date - doc.contract_date).days
        valid_range = (2, 45)  # Standard range
        results.append(ValidationResult(
            field="first_payment_timing",
            passed=valid_range[0] <= days_to_first <= valid_range[1],
            reason=f"First payment in {days_to_first} days (valid: {valid_range[0]}-{valid_range[1]})",
            severity="medium" if not (valid_range[0] <= days_to_first <= valid_range[1]) else "low",
            category="legal"
        ))
        
        # SSN consistency check
        ssn_consistent = self._check_ssn_consistency(doc)
        results.append(ValidationResult(
            field="ssn_consistency",
            passed=ssn_consistent,
            reason="SSN consistent across document" if ssn_consistent else "SSN inconsistencies found",
            severity="high" if not ssn_consistent else "low",
            category="compliance"
        ))
        
        return results
    
    def _validate_debt_composition(self, doc: ExtractedDocument) -> List[ValidationResult]:
        """Validate debt composition requirements."""
        results = []
        
        # Minimum 50% unsecured debt
        unsecured_debt = sum(
            c.current_balance for c in doc.creditors 
            if c.debt_type in [DebtType.CREDIT_CARD, DebtType.PERSONAL_LOAN, DebtType.COLLECTION]
        )
        unsecured_percentage = (unsecured_debt / doc.financial_analysis.total_enrolled_debt) * 100
        
        results.append(ValidationResult(
            field="unsecured_debt_percentage",
            passed=unsecured_percentage >= 50,
            reason=f"Unsecured debt: {unsecured_percentage:.1f}% (minimum: 50%)",
            severity="critical" if unsecured_percentage < 50 else "low",
            category="financial"
        ))
        
        # High-risk creditors check
        high_risk_found = [
            c.creditor_name for c in doc.creditors 
            if c.creditor_name.upper() in self.HIGH_RISK_CREDITORS
        ]
        results.append(ValidationResult(
            field="high_risk_creditors",
            passed=len(high_risk_found) == 0,
            reason=f"High-risk creditors: {', '.join(high_risk_found)}" if high_risk_found 
                   else "No high-risk creditors found",
            severity="high" if high_risk_found else "low",
            category="compliance"
        ))
        
        # Minimum debt per creditor
        small_debts = [
            c.creditor_name for c in doc.creditors 
            if c.current_balance < 250
        ]
        results.append(ValidationResult(
            field="minimum_debt_per_creditor",
            passed=len(small_debts) == 0,
            reason=f"Creditors below $250: {', '.join(small_debts)}" if small_debts 
                   else "All creditors meet minimum debt requirement",
            severity="medium" if small_debts else "low",
            category="financial"
        ))
        
        return results
    
    def _validate_program_structure(self, doc: ExtractedDocument) -> List[ValidationResult]:
        """Validate program structure requirements."""
        results = []
        
        # Program duration check
        max_duration = 60  # months
        results.append(ValidationResult(
            field="program_duration",
            passed=doc.financial_analysis.estimated_program_length <= max_duration,
            reason=f"Program length: {doc.financial_analysis.estimated_program_length} months (max: {max_duration})",
            severity="medium" if doc.financial_analysis.estimated_program_length > max_duration else "low",
            category="financial"
        ))
        
        # Settlement percentage validation
        settlement_percentage = (doc.financial_analysis.estimated_settlement_amount / 
                               doc.financial_analysis.total_enrolled_debt) * 100
        results.append(ValidationResult(
            field="settlement_percentage",
            passed=30 <= settlement_percentage <= 70,
            reason=f"Settlement percentage: {settlement_percentage:.1f}% (range: 30-70%)",
            severity="medium" if not (30 <= settlement_percentage <= 70) else "low",
            category="financial"
        ))
        
        return results
    
    def _validate_compliance_requirements(self, doc: ExtractedDocument) -> List[ValidationResult]:
        """Validate compliance and regulatory requirements."""
        results = []
        
        # State assignment validation
        state = doc.client_info.address.state
        expected_company = self.STATE_COMPANY_MAP.get(state, "Unknown")
        results.append(ValidationResult(
            field="state_assignment",
            passed=state in self.STATE_COMPANY_MAP,
            reason=f"State {state} assigned to {expected_company}" if state in self.STATE_COMPANY_MAP
                   else f"Unknown state assignment for {state}",
            severity="medium" if state not in self.STATE_COMPANY_MAP else "low",
            category="compliance"
        ))
        
        # VLP enrollment check (if applicable)
        if hasattr(doc, 'vlp_enrolled'):
            results.append(ValidationResult(
                field="vlp_enrollment",
                passed=True,  # Always passes, just informational
                reason=f"VLP enrolled: {doc.vlp_enrolled}",
                severity="low",
                category="compliance"
            ))
        
        return results
    
    def _check_ssn_consistency(self, doc: ExtractedDocument) -> bool:
        """
        Check SSN consistency across document sections.
        
        Args:
            doc: Document to check
            
        Returns:
            True if SSN is consistent
        """
        client_ssn = doc.client_info.ssn.replace('-', '').replace('X', '')
        
        # Check SSN in document sections
        for section in doc.document_sections:
            section_data = section.data
            if isinstance(section_data, dict):
                for key, value in section_data.items():
                    if 'ssn' in key.lower() and isinstance(value, str):
                        section_ssn = value.replace('-', '').replace('X', '')
                        if section_ssn and section_ssn != client_ssn:
                            logger.warning(f"SSN mismatch in section {section.section_name}")
                            return False
        
        return True
    
    def get_critical_failures(self, results: List[ValidationResult]) -> List[ValidationResult]:
        """Get list of critical validation failures."""
        return [r for r in results if r.is_critical]
    
    def get_blocking_failures(self, results: List[ValidationResult]) -> List[ValidationResult]:
        """Get list of blocking validation failures."""
        return [r for r in results if r.is_blocking]