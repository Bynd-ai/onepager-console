import uuid
import time
import logging
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
from .database_service import DatabaseService, OnePagerRecord

logger = logging.getLogger("RequestManager")


class RequestManager:
    """Manages concurrent requests and deduplication for one-pager generation"""

    def __init__(self):
        self.db_service = DatabaseService()

    def generate_request_id(self, company_name: str, website_url: str) -> str:
        """Generate a unique request ID based on company and timestamp"""
        timestamp = int(time.time() * 1000)
        safe_company = "".join([ch if ch.isalnum() else "_" for ch in company_name])
        return f"{safe_company}_{timestamp}_{uuid.uuid4().hex[:8]}"

    async def handle_new_request(
        self,
        company_name: str,
        website_url: str,
        session_id: Optional[str] = None,
        check_duplicates: bool = True,
        duplicate_window_minutes: int = 5
    ) -> Tuple[OnePagerRecord, bool]:
        """
        Handle a new one-pager request with deduplication and concurrency management

        Returns:
            Tuple[OnePagerRecord, bool]: (record, is_new_request)
            - If is_new_request=True: New record was created
            - If is_new_request=False: Existing record was found and returned
        """
        try:
            # Check for duplicate requests if enabled
            if check_duplicates:
                existing_record = await self.db_service.check_duplicate_request(
                    company_name, website_url, duplicate_window_minutes
                )

                if existing_record:
                    logger.info(f"Found duplicate request for {company_name}: {existing_record.request_id}")

                    # If the existing request is still in progress, return it
                    if existing_record.status == "in-progress":
                        logger.info(f"Returning existing in-progress request: {existing_record.request_id}")
                        return existing_record, False

                    # If the existing request completed recently, we might want to return it
                    # or create a new one depending on business logic
                    logger.info(f"Found recent completed request: {existing_record.request_id} (status: {existing_record.status})")
                    # For now, we'll create a new request even for completed ones
                    # This can be changed based on business requirements

            # Generate unique request ID
            request_id = self.generate_request_id(company_name, website_url)

            # Check if there are any in-progress requests for the same company
            in_progress_records = await self.db_service.get_in_progress_records_for_company(company_name)

            if in_progress_records:
                logger.warning(f"Found {len(in_progress_records)} in-progress requests for {company_name}")
                # We could implement queuing logic here, but for now we'll allow concurrent requests
                # Each will get its own unique request_id and be tracked separately

            # Create new record
            logger.info(f"Creating new request: {request_id} for {company_name}")
            return None, True  # Signal that a new record should be created

        except Exception as e:
            logger.error(f"Error handling new request for {company_name}: {str(e)}")
            raise

    async def create_request_record(
        self,
        company_name: str,
        website_url: str,
        request_id: str,
        session_id: Optional[str] = None,
        folder_title: str = "",
        base_path: str = "",
        container: str = "bynd-dev",
        excel_provided: bool = False,
        excel_filename: Optional[str] = None,
        excel_size: Optional[int] = None,
        excel_blob_url: Optional[str] = None,
        excel_blob_path: Optional[str] = None
    ) -> Optional[OnePagerRecord]:
        """Create a new request record in the database"""
        try:
            record = OnePagerRecord(
                request_id=request_id,
                session_id=session_id,
                company_name=company_name,
                website_url=website_url,
                status="in-progress",
                generated_at=datetime.utcnow().isoformat(),
                duration_ms=0,
                folder_title=folder_title,
                base_path=base_path,
                container=container,
                pptx_filename="",  # Will be updated later
                excel_provided=excel_provided,
                excel_filename=excel_filename,
                excel_size=excel_size,
                excel_blob_url=excel_blob_url,
                excel_blob_path=excel_blob_path,
            )

            created_record = await self.db_service.create_one_pager_record(record)
            if created_record:
                logger.info(f"Created request record: {request_id} with DB ID: {created_record.id}")
                return created_record
            else:
                logger.error(f"Failed to create request record: {request_id}")
                return None

        except Exception as e:
            logger.error(f"Error creating request record {request_id}: {str(e)}")
            return None

    async def update_request_status(
        self,
        request_id: str,
        status: str,
        update_data: Optional[Dict[str, Any]] = None,
        atomic: bool = True
    ) -> Optional[OnePagerRecord]:
        """Update the status of a request with optional atomic update"""
        try:
            # Get the current record
            current_record = await self.db_service.get_one_pager_record_by_request_id(request_id)
            if not current_record:
                logger.error(f"Request not found: {request_id}")
                return None

            # Prepare update data
            if update_data is None:
                update_data = {}

            update_data['status'] = status

            # Use atomic update if requested
            if atomic:
                updated_record = await self.db_service.update_one_pager_record_atomic(
                    current_record.id,
                    update_data,
                    expected_status=current_record.status
                )
            else:
                updated_record = await self.db_service.update_one_pager_record(
                    current_record.id,
                    update_data
                )

            if updated_record:
                logger.info(f"Updated request {request_id} to status: {status}")
                return updated_record
            else:
                logger.error(f"Failed to update request {request_id} to status: {status}")
                return None

        except Exception as e:
            logger.error(f"Error updating request {request_id}: {str(e)}")
            return None

    async def get_request_status(self, request_id: str) -> Optional[Dict[str, Any]]:
        """Get the current status of a request"""
        try:
            record = await self.db_service.get_one_pager_record_by_request_id(request_id)
            if record:
                return {
                    "request_id": record.request_id,
                    "status": record.status,
                    "company_name": record.company_name,
                    "website_url": record.website_url,
                    "created_at": record.created_at,
                    "updated_at": record.updated_at,
                    "duration_ms": record.duration_ms,
                    "pptx_blob_url": record.pptx_blob_url,
                    "excel_blob_url": record.excel_blob_url,
                    "excel_provided": record.excel_provided,
                    "excel_filename": record.excel_filename,
                    "error_message": record.error_message,
                    "warnings": record.warnings
                }
            else:
                return None

        except Exception as e:
            logger.error(f"Error getting request status {request_id}: {str(e)}")
            return None

    async def cleanup_stale_requests(self, stale_hours: int = 24) -> int:
        """Clean up stale in-progress requests that are older than specified hours"""
        try:
            from datetime import timedelta
            cutoff_time = (datetime.utcnow() - timedelta(hours=stale_hours)).isoformat()

            # Get stale in-progress records
            result = self.db_service.client.table('one_pager_reports').select('id,request_id').eq('status', 'in-progress').lt('created_at', cutoff_time).execute()

            if not result.data:
                return 0

            # Update them to error status
            stale_ids = [record['id'] for record in result.data]
            update_data = {
                'status': 'error',
                'error_type': 'timeout',
                'error_message': f'Request timed out after {stale_hours} hours',
                'updated_at': datetime.utcnow().isoformat()
            }

            result = self.db_service.client.table('one_pager_reports').update(update_data).in_('id', stale_ids).execute()

            cleaned_count = len(result.data) if result.data else 0
            logger.info(f"Cleaned up {cleaned_count} stale requests")
            return cleaned_count

        except Exception as e:
            logger.error(f"Error cleaning up stale requests: {str(e)}")
            return 0


# Global instance
request_manager = RequestManager()
