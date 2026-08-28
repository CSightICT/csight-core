"""Composition root for immutable Review Reports and tenant PoC metrics."""

from app.adapters.persistence.engine import get_engine
from app.adapters.persistence.poc_reporting import SQLAlchemyPocReportingRepository
from app.adapters.persistence.session import create_session_factory
from app.application.poc_reporting import (
    CreateCustomerCommunicationSimulation,
    GetCaseReviewReport,
    GetDataAssetSummary,
    GetPocSummary,
    ListCustomerCommunicationSimulations,
)
from app.bootstrap.settings import Settings
from app.interface.http.poc_reporting_services import PocReportingServiceContainer


def poc_reporting_is_configured(settings: Settings) -> bool:
    return settings.database_url_value is not None


def build_poc_reporting_services(settings: Settings) -> PocReportingServiceContainer:
    repository = SQLAlchemyPocReportingRepository(create_session_factory(get_engine(settings)))
    return PocReportingServiceContainer(
        get_case_review_report=GetCaseReviewReport(repository),
        get_poc_summary=GetPocSummary(repository),
        create_customer_communication=CreateCustomerCommunicationSimulation(repository),
        list_customer_communications=ListCustomerCommunicationSimulations(repository),
        get_data_asset_summary=GetDataAssetSummary(repository),
    )


__all__ = ["build_poc_reporting_services", "poc_reporting_is_configured"]
