# services/document-parser/src/models/base.py
"""Base data models for document parsing."""

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class DebtType(str, Enum):
    """Enum for debt types."""
    CREDIT_CARD = "Credit Card"
    INSTALLMENT = "Installment"
    PERSONAL_LOAN = "Personal Loan"
    COLLECTION = "Collection"
    MEDICAL = "Medical"
    OTHER = "Other"


class AccountType(str, Enum):
    """Enum for bank account types."""
    CHECKING = "Checking"
    SAVINGS = "Savings"


class Address(BaseModel):
    """Model for address information."""
    street: str
    city: str
    state: str = Field(..., pattern="^[A-Z]{2}$")
    zip_code: str = Field(..., pattern="^\\d{5}(-\\d{4})?$")
    
    def formatted(self) -> str:
        """Return formatted address string."""
        return f"{self.street}\n{self.city}, {self.state} {self.zip_code}"


class Creditor(BaseModel):
    """Model for creditor information."""
    creditor_name: str
    account_name: str
    current_balance: float = Field(gt=0)
    debt_type: DebtType
    account_number: Optional[str] = None
    
    @field_validator('current_balance')
    def validate_balance(cls, v):
        """Validate minimum balance requirement."""
        if v < 250:
            raise ValueError("Minimum debt per creditor is $250")
        return v


class BankDetails(BaseModel):
    """Model for bank account information."""
    bank_name: str
    account_number: str
    routing_number: Optional[str] = None
    account_type: AccountType


class ClientInformation(BaseModel):
    """Model for client information."""
    name: str
    ssn: str = Field(..., pattern="^(\\d{3}-\\d{2}-\\d{4}|XXX-XX-\\d{4})$")
    dob: date
    email: str = Field(..., pattern="^[\\w\\.-]+@[\\w\\.-]+\\.\\w+$")
    phone: str = Field(..., pattern="^\\d{3}-\\d{3}-\\d{4}$")
    address: Address
    
    @field_validator('dob')
    def validate_age(cls, v):
        """Validate client is at least 18 years old."""
        today = date.today()
        age = today.year - v.year - ((today.month, today.day) < (v.month, v.day))
        if age < 18:
            raise ValueError("Client must be 18 or older")
        return v


class FinancialAnalysis(BaseModel):
    """Model for financial analysis section."""
    monthly_income: float = Field(gt=0)
    monthly_expenses: float = Field(ge=0)
    net_income: float
    total_enrolled_debt: float = Field(gt=0)
    estimated_program_length: int = Field(gt=0, le=72)
    monthly_program_deposit: float = Field(ge=250)
    estimated_settlement_amount: float
    total_program_fees: float
    estimated_savings: float
    estimated_total_cost: float
    
    @field_validator('net_income')
    def validate_net_income(cls, v, values):
        """Validate net income calculation."""
        if 'monthly_income' in values.data and 'monthly_expenses' in values.data:
            expected = values.data['monthly_income'] - values.data['monthly_expenses']
            if abs(v - expected) > 0.01:
                raise ValueError("Net income calculation mismatch")
        return v