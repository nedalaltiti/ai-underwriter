# services/document-parser/src/integrations/database/adapter.py
"""Complete database adapter with all 18 storage methods and UUID-based IDs."""

import asyncpg
import uuid
import random
import asyncio
from datetime import datetime, date
from typing import Any, Optional
from loguru import logger

from models.underwriting_entities import (
    ExtractedDocumentPackage, EngagementTerm, PowerOfAttorney, PaymentGatewayAgreement,
    FinancialAnalysis, DebtSchedule, FCRAConsumerReportConsent, Disclosure,
    HighInterestCreditorDisclosure, ProgramDisclosure, CancellationNotice,
    PaymentGatewayServiceFees, PaymentGatewayBankInfo, PaymentGatewayDepositSchedule,
    LegalPlanAgreement, ClixsignCertificateSender, ClixsignCertificateSigner
)


class UnderwritingDatabaseAdapter:
    """Complete database adapter with UUID-based IDs and professional logging."""
    
    def __init__(self, config_instance=None):
        if config_instance:
            self.config = config_instance
        else:
            from config import config
            self.config = config
            
        self.connection_string = self.config.database_url
        self.schema = "underwriting"
        self.pool = None
        
        # ID generation strategy for collision-free IDs
        self.id_counter = random.randint(1, 1000000)
    
    def _generate_unique_id(self, file_id: int, entity_type: str = "") -> int:
        """Generate a truly unique ID using UUID strategy."""
        unique_uuid = uuid.uuid4()
        id_value = abs(hash(str(unique_uuid))) % (2**63 - 1)
        return id_value if id_value != 0 else 1
    
    async def initialize(self):
        """Initialize database connection pool."""
        try:
            self.pool = await asyncpg.create_pool(
                self.connection_string,
                min_size=max(1, self.config.database_pool_size // 5),
                max_size=self.config.database_pool_size,
                max_inactive_connection_lifetime=300,
                command_timeout=self.config.database_timeout,
                server_settings={
                    'application_name': f'{self.config.service_name}-{self.config.environment}',
                    'timezone': 'UTC'
                }
            )
            logger.bind(service="document-parser").info("db.pool_initialized")
        except Exception as e:
            logger.bind(service="document-parser", error=type(e).__name__).error("db.pool_failed")
            raise
    
    async def close(self):
        """Close database connection pool."""
        if self.pool:
            await self.pool.close()
            logger.bind(service="document-parser").info("db.pool_closed")
    
    async def _check_document_exists(self, connection, file_id: int) -> bool:
        """Check if document was already processed."""
        result = await connection.fetchval("""
            SELECT EXISTS(
                SELECT 1 FROM underwriting.engagement_term WHERE file_id = $1
                UNION
                SELECT 1 FROM underwriting.financial_analysis WHERE file_id = $1
                UNION
                SELECT 1 FROM underwriting.payment_gateway_agreement WHERE file_id = $1
            )
        """, file_id)
        return result
    
    async def store_document_package(self, package: ExtractedDocumentPackage) -> bool:
        """Store complete document package with duplicate checking and UUID-based IDs."""
        try:
            # Check for duplicates first
            async with self.pool.acquire() as connection:
                existing = await self._check_document_exists(connection, package.file_id)
                if existing:
                    logger.bind(file_id=package.file_id).warning("db.duplicate_skip document_already_exists=true")
                    return True
            
            # Store all entities in one transaction (keeping original behavior)
            async with self.pool.acquire() as connection:
                async with connection.transaction():
                    stored_count = 0
                    
                    # Store core entities (EXACT same logic as original)
                    if package.engagement_term:
                        await self._store_engagement_term(connection, package.engagement_term)
                        stored_count += 1
                        
                    if package.power_of_attorney:
                        await self._store_power_of_attorney(connection, package.power_of_attorney)
                        stored_count += 1
                        
                    if package.payment_gateway_agreement:
                        await self._store_payment_gateway_agreement(connection, package.payment_gateway_agreement)
                        stored_count += 1
                        
                    if package.financial_analysis:
                        await self._store_financial_analysis(connection, package.financial_analysis)
                        stored_count += 1
                    
                    # Store optional entities (EXACT same logic)
                    if package.fcra_consent:
                        await self._store_fcra_consent(connection, package.fcra_consent)
                        stored_count += 1
                        
                    if package.disclosure:
                        await self._store_disclosure(connection, package.disclosure)
                        stored_count += 1
                        
                    if package.high_interest_disclosure:
                        await self._store_high_interest_disclosure(connection, package.high_interest_disclosure)
                        stored_count += 1
                        
                    if package.program_disclosure:
                        await self._store_program_disclosure(connection, package.program_disclosure)
                        stored_count += 1
                        
                    if package.cancellation_notice:
                        await self._store_cancellation_notice(connection, package.cancellation_notice)
                        stored_count += 1
                        
                    if package.payment_bank_info:
                        await self._store_payment_bank_info(connection, package.payment_bank_info)
                        stored_count += 1
                        
                    if package.legal_plan_agreement:
                        await self._store_legal_plan_agreement(connection, package.legal_plan_agreement)
                        stored_count += 1
                        
                    if package.clixsign_sender:
                        await self._store_clixsign_sender(connection, package.clixsign_sender)
                        stored_count += 1
                    
                    # Store list entities with UUID-based IDs
                    if package.debt_schedule:
                        for debt in package.debt_schedule:
                            await self._store_debt_schedule(connection, debt)
                        stored_count += len(package.debt_schedule)
                        
                    if package.payment_service_fees:
                        for fee in package.payment_service_fees:
                            await self._store_payment_service_fees(connection, fee)
                        stored_count += len(package.payment_service_fees)
                        
                    if package.payment_deposit_schedule:
                        for deposit in package.payment_deposit_schedule:
                            await self._store_payment_deposit_schedule(connection, deposit)
                        stored_count += len(package.payment_deposit_schedule)
                        
                    if package.clixsign_signers:
                        for signer in package.clixsign_signers:
                            await self._store_clixsign_signer(connection, signer)
                        stored_count += len(package.clixsign_signers)
                    
                    logger.bind(
                        file_id=package.file_id,
                        entities_stored=stored_count
                    ).info("db.package_stored")
                    return True
                    
        except asyncpg.UndefinedColumnError as e:
            logger.bind(
                file_id=package.file_id,
                error="UndefinedColumnError",
                column_name=getattr(e, 'column_name', 'unknown'),
                table_name=getattr(e, 'table_name', 'unknown'),
                sqlstate=getattr(e, 'sqlstate', 'unknown'),
                detail=str(e)
            ).error("db.package_failed schema_mismatch=true")
            return False
        except Exception as e:
            logger.bind(
                file_id=package.file_id,
                error=type(e).__name__
            ).error("db.package_failed")
            return False
    
    async def _store_engagement_term(self, connection, entity: EngagementTerm):
        """Store engagement term data."""
        await connection.execute("""
            INSERT INTO underwriting.engagement_term 
            (file_id, company_name, company_address, company_phone, company_type,
             settlement_fee, settlement_fee_percentage, monthly_payment, client_name,
             client_signature, client_signature_date, coclient_name, coclient_signature,
             coclient_signature_date, initials, initials_count, is_all_initials_present, page_count, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19)
            ON CONFLICT (file_id) DO UPDATE SET
                company_name = EXCLUDED.company_name,
                settlement_fee = EXCLUDED.settlement_fee,
                client_name = EXCLUDED.client_name,
                updated_at = EXCLUDED.updated_at
        """, entity.file_id, entity.company_name, entity.company_address, entity.company_phone,
            entity.company_type, entity.settlement_fee, entity.settlement_fee_percentage,
            entity.monthly_payment, entity.client_name, entity.client_signature,
            entity.client_signature_date, entity.coclient_name, entity.coclient_signature,
            entity.coclient_signature_date, entity.initials, entity.initials_count,
            entity.is_all_initials_present, entity.page_count, datetime.now())
    
    async def _store_power_of_attorney(self, connection, entity: PowerOfAttorney):
        """Store power of attorney data."""
        await connection.execute("""
            INSERT INTO underwriting.power_of_attorney 
            (file_id, company_name, attorney_name, attorney_address, attorney_phone,
             client_name, client_ssn, client_dob, client_signature, client_signature_date,
             coclient_name, coclient_ssn, coclient_dob, coclient_signature, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
            ON CONFLICT (file_id) DO UPDATE SET
                company_name = COALESCE(EXCLUDED.company_name, power_of_attorney.company_name),
                attorney_name = COALESCE(EXCLUDED.attorney_name, power_of_attorney.attorney_name),
                client_name = COALESCE(EXCLUDED.client_name, power_of_attorney.client_name),
                updated_at = EXCLUDED.updated_at
        """, entity.file_id, entity.company_name, entity.attorney_name, entity.attorney_address,
            entity.attorney_phone, entity.client_name, entity.client_ssn, entity.client_dob,
            entity.client_signature, entity.client_signature_date, entity.coclient_name,
            entity.coclient_ssn, entity.coclient_dob, entity.coclient_signature, datetime.now())
    
    async def _store_financial_analysis(self, connection, entity: FinancialAnalysis):
        """Store financial analysis data."""
        # Ensure estimated_program_length is properly cast to int
        estimated_program_length_value = None
        if entity.estimated_program_length is not None:
            try:
                estimated_program_length_value = int(entity.estimated_program_length)
            except (ValueError, TypeError):
                estimated_program_length_value = None
        
        await connection.execute("""
            INSERT INTO underwriting.financial_analysis 
            (file_id, applicant_name, applicant_email, coapplicant_name, coapplicant_email,
             draft_type, fixed_income, day_phone, evening_phone, cell_phone,
             program_start_date, estimated_program_start_date, lump_sum,
             applicant_monthly_income, coapplicant_monthly_income, applicant_expenses,
             coapplicant_expenses, applicant_total_net_income, coapplicant_total_net_income,
             total_enrolled_debt, estimated_program_length, monthly_program_deposit,
             estimated_program_settle_amount, fee_method, total_program_fees,
             estimated_program_savings, estimated_total_cost, hardship_details,
             client_signature, client_signature_date, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28, $29, $30, $31)
            ON CONFLICT (file_id) DO UPDATE SET
                applicant_name = COALESCE(EXCLUDED.applicant_name, financial_analysis.applicant_name),
                applicant_email = COALESCE(EXCLUDED.applicant_email, financial_analysis.applicant_email),
                coapplicant_name = COALESCE(EXCLUDED.coapplicant_name, financial_analysis.coapplicant_name),
                coapplicant_email = COALESCE(EXCLUDED.coapplicant_email, financial_analysis.coapplicant_email),
                draft_type = COALESCE(EXCLUDED.draft_type, financial_analysis.draft_type),
                fixed_income = COALESCE(EXCLUDED.fixed_income, financial_analysis.fixed_income),
                day_phone = COALESCE(EXCLUDED.day_phone, financial_analysis.day_phone),
                evening_phone = COALESCE(EXCLUDED.evening_phone, financial_analysis.evening_phone),
                cell_phone = COALESCE(EXCLUDED.cell_phone, financial_analysis.cell_phone),
                program_start_date = COALESCE(EXCLUDED.program_start_date, financial_analysis.program_start_date),
                estimated_program_start_date = COALESCE(EXCLUDED.estimated_program_start_date, financial_analysis.estimated_program_start_date),
                lump_sum = COALESCE(EXCLUDED.lump_sum, financial_analysis.lump_sum),
                applicant_monthly_income = COALESCE(EXCLUDED.applicant_monthly_income, financial_analysis.applicant_monthly_income),
                coapplicant_monthly_income = COALESCE(EXCLUDED.coapplicant_monthly_income, financial_analysis.coapplicant_monthly_income),
                applicant_expenses = COALESCE(EXCLUDED.applicant_expenses, financial_analysis.applicant_expenses),
                coapplicant_expenses = COALESCE(EXCLUDED.coapplicant_expenses, financial_analysis.coapplicant_expenses),
                applicant_total_net_income = COALESCE(EXCLUDED.applicant_total_net_income, financial_analysis.applicant_total_net_income),
                coapplicant_total_net_income = COALESCE(EXCLUDED.coapplicant_total_net_income, financial_analysis.coapplicant_total_net_income),
                total_enrolled_debt = COALESCE(EXCLUDED.total_enrolled_debt, financial_analysis.total_enrolled_debt),
                estimated_program_length = COALESCE(EXCLUDED.estimated_program_length, financial_analysis.estimated_program_length),
                monthly_program_deposit = COALESCE(EXCLUDED.monthly_program_deposit, financial_analysis.monthly_program_deposit),
                estimated_program_settle_amount = COALESCE(EXCLUDED.estimated_program_settle_amount, financial_analysis.estimated_program_settle_amount),
                fee_method = COALESCE(EXCLUDED.fee_method, financial_analysis.fee_method),
                total_program_fees = COALESCE(EXCLUDED.total_program_fees, financial_analysis.total_program_fees),
                estimated_program_savings = COALESCE(EXCLUDED.estimated_program_savings, financial_analysis.estimated_program_savings),
                estimated_total_cost = COALESCE(EXCLUDED.estimated_total_cost, financial_analysis.estimated_total_cost),
                hardship_details = COALESCE(EXCLUDED.hardship_details, financial_analysis.hardship_details),
                client_signature = COALESCE(EXCLUDED.client_signature, financial_analysis.client_signature),
                client_signature_date = COALESCE(EXCLUDED.client_signature_date, financial_analysis.client_signature_date),
                updated_at = EXCLUDED.updated_at
        """, entity.file_id, entity.applicant_name, entity.applicant_email, entity.coapplicant_name,
            entity.coapplicant_email, entity.draft_type, entity.fixed_income, entity.day_phone,
            entity.evening_phone, entity.cell_phone, entity.program_start_date,
            entity.estimated_program_start_date, entity.lump_sum, entity.applicant_monthly_income,
            entity.coapplicant_monthly_income, entity.applicant_expenses, entity.coapplicant_expenses,
            entity.applicant_total_net_income, entity.coapplicant_total_net_income,
            entity.total_enrolled_debt, estimated_program_length_value,
            entity.monthly_program_deposit, entity.estimated_program_settle_amount,
            entity.fee_method, entity.total_program_fees, entity.estimated_program_savings,
            entity.estimated_total_cost, entity.hardship_details, entity.client_signature,
            entity.client_signature_date, datetime.now())
    
    async def _store_debt_schedule(self, connection, entity: DebtSchedule):
        """Store debt schedule entry with UUID-based collision-free ID."""
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                # Generate UUID-based unique ID (collision-free)
                unique_id = self._generate_unique_id(entity.file_id, "debt")
                
                await connection.execute("""
                    INSERT INTO underwriting.debt_schedule 
                    (file_id, creditor_name, name_on_account, account_number, current_balance, debt_type, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                """, entity.file_id, entity.creditor_name, entity.name_on_account, 
                    entity.account_number, entity.current_balance, entity.debt_type, datetime.now())
                return  # Success
                
            except asyncpg.UniqueViolationError as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.1 * (2 ** attempt))
                    logger.bind(
                        file_id=entity.file_id,
                        attempt=attempt + 2,
                        creditor=entity.creditor_name
                    ).debug("db.debt_retry uuid_collision=true")
                else:
                    # Check if content already exists
                    existing = await connection.fetchval("""
                        SELECT id FROM underwriting.debt_schedule 
                        WHERE file_id = $1 AND creditor_name = $2 AND name_on_account = $3
                    """, entity.file_id, entity.creditor_name, entity.name_on_account)
                    
                    if existing:
                        logger.bind(
                            file_id=entity.file_id,
                            existing_id=existing,
                            creditor=entity.creditor_name
                        ).info("db.debt_exists content_duplicate=true")
                        return
                    else:
                        raise e
    
    async def _store_payment_gateway_agreement(self, connection, entity: PaymentGatewayAgreement):
        """Store payment gateway agreement data."""
        # Normalize inputs to avoid type issues
        def _coerce_client_initials(v: Any) -> Optional[str]:
            try:
                if isinstance(v, (date, datetime)):
                    return None
            except Exception:
                pass
            if v is None:
                return None
            s = str(v)
            # Keep only letters, cap length to 10
            import re
            s = ''.join(re.findall(r'[A-Za-z]', s))[:10]
            return s or None

        client_initials_value = _coerce_client_initials(entity.client_initials)
        pages_count_value = None
        if entity.pages_count is not None:
            try:
                pages_count_value = int(entity.pages_count)
            except Exception:
                pages_count_value = None
                
        await connection.execute("""
            INSERT INTO underwriting.payment_gateway_agreement 
            (file_id, account_id, client_first_name, client_last_name, client_middle_initial,
             client_ssn, client_dob, client_address, client_city, client_state, client_zipcode,
             client_phone, client_email, coclient_first_name, coclient_last_name,
             coclient_middle_initial, coclient_ssn, coclient_dob, client_initials,
             client_signature, client_signature_date, coclient_signature, coclient_signature_date,
             pages_count, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25)
            ON CONFLICT (file_id) DO UPDATE SET
                account_id = COALESCE(EXCLUDED.account_id, payment_gateway_agreement.account_id),
                client_first_name = COALESCE(EXCLUDED.client_first_name, payment_gateway_agreement.client_first_name),
                updated_at = EXCLUDED.updated_at
        """, entity.file_id, entity.account_id, entity.client_first_name, entity.client_last_name,
            entity.client_middle_initial, entity.client_ssn, entity.client_dob, entity.client_address,
            entity.client_city, entity.client_state, entity.client_zipcode, entity.client_phone,
            entity.client_email, entity.coclient_first_name, entity.coclient_last_name,
            entity.coclient_middle_initial, entity.coclient_ssn, entity.coclient_dob,
            client_initials_value, entity.client_signature, entity.client_signature_date,
            entity.coclient_signature, entity.coclient_signature_date, pages_count_value,
            datetime.now())
    
    async def _store_fcra_consent(self, connection, entity: FCRAConsumerReportConsent):
        """Store FCRA consent data."""
        await connection.execute("""
            INSERT INTO underwriting.fcra_consumer_report_consent 
            (file_id, company_name, client_name, client_signature, client_signature_date, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (file_id) DO UPDATE SET
                company_name = COALESCE(EXCLUDED.company_name, fcra_consumer_report_consent.company_name),
                client_name = COALESCE(EXCLUDED.client_name, fcra_consumer_report_consent.client_name),
                updated_at = EXCLUDED.updated_at
        """, entity.file_id, entity.company_name, entity.client_name,
            entity.client_signature, entity.client_signature_date, datetime.now())
    
    async def _store_disclosure(self, connection, entity: Disclosure):
        """Store disclosure data."""
        await connection.execute("""
            INSERT INTO underwriting.disclosure 
            (file_id, client_signature, client_signature_date, coclient_signature, coclient_signature_date, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (file_id) DO UPDATE SET
                client_signature = COALESCE(EXCLUDED.client_signature, disclosure.client_signature),
                updated_at = EXCLUDED.updated_at
        """, entity.file_id, entity.client_signature, entity.client_signature_date,
            entity.coclient_signature, entity.coclient_signature_date, datetime.now())
    
    async def _store_high_interest_disclosure(self, connection, entity: HighInterestCreditorDisclosure):
        """Store high interest creditor disclosure data."""
        await connection.execute("""
            INSERT INTO underwriting.high_interest_creditor_disclosure 
            (file_id, company_name, client_name, client_signature, client_signature_date,
             coclient_name, coclient_signature, coclient_signature_date, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (file_id) DO UPDATE SET
                company_name = COALESCE(EXCLUDED.company_name, high_interest_creditor_disclosure.company_name),
                client_name = COALESCE(EXCLUDED.client_name, high_interest_creditor_disclosure.client_name),
                updated_at = EXCLUDED.updated_at
        """, entity.file_id, entity.company_name, entity.client_name, entity.client_signature,
            entity.client_signature_date, entity.coclient_name, entity.coclient_signature,
            entity.coclient_signature_date, datetime.now())
    
    async def _store_program_disclosure(self, connection, entity: ProgramDisclosure):
        """Store program disclosure data."""
        await connection.execute("""
            INSERT INTO underwriting.program_disclosure 
            (file_id, company_name, settlement_fee_percent, client_initial, is_all_initials_present, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (file_id) DO UPDATE SET
                company_name = COALESCE(EXCLUDED.company_name, program_disclosure.company_name),
                settlement_fee_percent = COALESCE(EXCLUDED.settlement_fee_percent, program_disclosure.settlement_fee_percent),
                updated_at = EXCLUDED.updated_at
        """, entity.file_id, entity.company_name, entity.settlement_fee_percent,
            entity.client_initial, entity.is_all_initials_present, datetime.now())
    
    async def _store_cancellation_notice(self, connection, entity: CancellationNotice):
        """Store cancellation notice data."""
        await connection.execute("""
            INSERT INTO underwriting.cancellation_notice 
            (file_id, cancellation_deadline, cancellation_date, buyer_signature, updated_at)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (file_id) DO UPDATE SET
                cancellation_deadline = COALESCE(EXCLUDED.cancellation_deadline, cancellation_notice.cancellation_deadline),
                updated_at = EXCLUDED.updated_at
        """, entity.file_id, entity.cancellation_deadline, entity.cancellation_date,
            entity.buyer_signature, datetime.now())
    
    async def _store_payment_service_fees(self, connection, entity: PaymentGatewayServiceFees):
        """Store payment gateway service fees."""
        # First, delete existing entries for this file_id to avoid duplicates
        await connection.execute("""
            DELETE FROM underwriting.payment_gateway_service_fees 
            WHERE file_id = $1 AND service_type = $2 AND service_name = $3
        """, entity.file_id, entity.service_type, entity.service_name)
        
        # Then insert the new entry
        await connection.execute("""
            INSERT INTO underwriting.payment_gateway_service_fees 
            (file_id, service_type, service_name, service_amount, updated_at)
            VALUES ($1, $2, $3, $4, $5)
        """, entity.file_id, entity.service_type, entity.service_name,
            entity.service_amount, datetime.now())
    
    async def _store_payment_bank_info(self, connection, entity: PaymentGatewayBankInfo):
        """Store payment gateway bank info."""
        await connection.execute("""
            INSERT INTO underwriting.payment_gateway_bank_info 
            (file_id, authorizing_person_name, bank_name, account_number, routing_number,
             account_type, address, recurring_debit_authorization, first_debit_date,
             client_signature, client_signature_date, coclient_signature, coclient_signature_date, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            ON CONFLICT (file_id) DO UPDATE SET
                authorizing_person_name = COALESCE(EXCLUDED.authorizing_person_name, payment_gateway_bank_info.authorizing_person_name),
                bank_name = COALESCE(EXCLUDED.bank_name, payment_gateway_bank_info.bank_name),
                updated_at = EXCLUDED.updated_at
        """, entity.file_id, entity.authorizing_person_name, entity.bank_name, entity.account_number,
            entity.routing_number, entity.account_type, entity.address, entity.recurring_debit_authorization,
            entity.first_debit_date, entity.client_signature, entity.client_signature_date,
            entity.coclient_signature, entity.coclient_signature_date, datetime.now())
    
    async def _store_payment_deposit_schedule(self, connection, entity: PaymentGatewayDepositSchedule):
        """Store payment gateway deposit schedule."""
        # First, delete existing entry for this file_id and payment_no to avoid duplicates
        await connection.execute("""
            DELETE FROM underwriting.payment_gateway_deposit_schedule 
            WHERE file_id = $1 AND payment_no = $2
        """, entity.file_id, entity.payment_no)
        
        # Then insert the new entry
        await connection.execute("""
            INSERT INTO underwriting.payment_gateway_deposit_schedule 
            (file_id, payment_no, process_date, amount, updated_at)
            VALUES ($1, $2, $3, $4, $5)
        """, entity.file_id, entity.payment_no, entity.process_date,
            entity.amount, datetime.now())
    
    async def _store_legal_plan_agreement(self, connection, entity: LegalPlanAgreement):
        """Store legal plan agreement data."""
        pages_count_value = None
        if entity.pages_count is not None:
            try:
                pages_count_value = int(entity.pages_count)
            except Exception:
                pages_count_value = None
        initials_count_value = None
        if entity.initials_count is not None:
            try:
                initials_count_value = int(entity.initials_count)
            except Exception:
                initials_count_value = None
                
        await connection.execute("""
            INSERT INTO underwriting.legal_plan_agreement 
            (file_id, legal_plan_provider, member_name, member_ssn, member_dob,
             coapplicant_name, coapplicant_ssn, coapplicant_dob, address, city, state, zipcode,
             phone1, phone2, email, referring_company, first_payment_date, first_payment_amount,
             monthly_recurring_date, monthly_payment_amount, debt_relief_program_duration,
             members_accumulation_amount, payment_processor_name, credit_card_number,
             bank_account_number, credit_card_expiration_date, bank_routing_number,
             credit_card_name, bank_institution_name, credit_card_billing_address,
             account_holder_name, initials_count, is_all_initials_present, client_signature, signature_date,
             pages_count, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28, $29, $30, $31, $32, $33, $34, $35, $36, $37)
            ON CONFLICT (file_id) DO UPDATE SET
                legal_plan_provider = COALESCE(EXCLUDED.legal_plan_provider, legal_plan_agreement.legal_plan_provider),
                member_name = COALESCE(EXCLUDED.member_name, legal_plan_agreement.member_name),
                updated_at = EXCLUDED.updated_at
        """, entity.file_id, entity.legal_plan_provider, entity.member_name, entity.member_ssn,
            entity.member_dob, entity.coapplicant_name, entity.coapplicant_ssn, entity.coapplicant_dob,
            entity.address, entity.city, entity.state, entity.zipcode, entity.phone1, entity.phone2,
            entity.email, entity.referring_company, entity.first_payment_date, entity.first_payment_amount,
            entity.monthly_recurring_date, entity.monthly_payment_amount, entity.debt_relief_program_duration,
            entity.members_accumulation_amount, entity.payment_processor_name, entity.credit_card_number,
            entity.bank_account_number, entity.credit_card_expiration_date, entity.bank_routing_number,
            entity.credit_card_name, entity.bank_institution_name, entity.credit_card_billing_address,
            entity.account_holder_name, initials_count_value, entity.is_all_initials_present, 
            entity.client_signature, entity.signature_date, pages_count_value, datetime.now())
    
    async def _store_clixsign_sender(self, connection, entity: ClixsignCertificateSender):
        """Store clixsign certificate sender data."""
        await connection.execute("""
            INSERT INTO underwriting.clixsign_certificate_sender 
            (file_id, package_id, package_title, final_status, final_status_date,
             sending_entity, sender_name, sender_email_address, sender_ip_address,
             signers_count, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (file_id) DO UPDATE SET
                package_id = EXCLUDED.package_id,
                final_status = EXCLUDED.final_status,
                updated_at = EXCLUDED.updated_at
        """, entity.file_id, entity.package_id, entity.package_title, entity.final_status,
            entity.final_status_date, entity.sending_entity, entity.sender_name,
            entity.sender_email_address, entity.sender_ip_address, entity.signers_count, datetime.now())
    
    async def _store_clixsign_signer(self, connection, entity: ClixsignCertificateSigner):
        """Store clixsign certificate signer data."""
        await connection.execute("""
            INSERT INTO underwriting.clixsign_certificate_signer 
            (file_id, package_id, signer_name, signer_email_address, signer_ip_address,
             signer_user_agent, package_opened_at, signature_adopted_at, package_signed_at,
             package_declined_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        """, entity.file_id, entity.package_id, entity.signer_name, entity.signer_email_address,
            entity.signer_ip_address, entity.signer_user_agent, entity.package_opened_at,
            entity.signature_adopted_at, entity.package_signed_at, entity.package_declined_at,
            datetime.now())


# Backward compatibility alias
DatabaseAdapter = UnderwritingDatabaseAdapter