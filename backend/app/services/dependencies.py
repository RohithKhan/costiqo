from app.services.account_service import AccountService
from app.core.config import Settings, get_settings
from app.services.auth_service import AuthService
from app.services.candidate_validation_service import CandidateValidationService
from app.services.comparison_service import ComparisonService
from app.services.decision_service import DecisionService
from app.services.history_service import HistoryService
from app.services.offer_verification_service import OfferVerificationService
from app.services.procurement_service import ProcurementService
from app.services.product_service import ProductService
from app.services.query_cache_store import QueryCacheStore
from app.services.queue_service import QueueService
from app.services.scrape_service import ScrapeService
from app.services.search_context_service import SearchContextService
from app.services.search_progress_service import SearchProgressService
from app.services.sentiment_service import SentimentService
from app.services.source_registry import SourceRegistry


settings = get_settings()
source_registry = SourceRegistry(settings)
sentiment_service = SentimentService()
procurement_service = ProcurementService()
search_context_service = SearchContextService()
search_progress_service = SearchProgressService(settings.redis_url)
auth_service = AuthService()
history_service = HistoryService()
decision_service = DecisionService()
query_cache_store = QueryCacheStore(settings.redis_url)
candidate_validation_service = CandidateValidationService(
    api_key=settings.openrouter_key,
    model=settings.openrouter_model,
    enabled=settings.llm_validation_enabled and settings.environment != "test",
    timeout_seconds=settings.llm_validation_timeout_seconds,
    max_candidates=settings.llm_validation_max_candidates,
    batch_size=settings.llm_validation_batch_size,
    parallel_batches=settings.llm_validation_parallel_batches,
)
offer_verification_service = OfferVerificationService(
    enabled=settings.offer_verification_enabled,
    timeout_seconds=settings.offer_verification_timeout_seconds,
    cache_ttl_seconds=settings.offer_verification_cache_ttl_seconds,
    max_offers=settings.offer_verification_max_offers,
)
scrape_service = ScrapeService(
    scrapers_by_source=source_registry.build_scrapers_by_source(),
    primary_sources=settings.primary_sources,
    background_sources=settings.background_sources,
    sentiment_service=sentiment_service,
    query_cache_store=query_cache_store,
    cache_ttl_seconds=settings.scrape_cache_ttl_seconds,
    background_cache_ttl_seconds=settings.background_scrape_cache_ttl_seconds,
    retry_attempts=settings.scrape_retry_attempts,
    retry_backoff_seconds=settings.scrape_retry_backoff_seconds,
)
queue_service = QueueService(
    queue_backend=settings.queue_backend,
    queue_name=settings.queue_name,
    queue_job_timeout_seconds=settings.queue_job_timeout_seconds,
    queue_result_ttl_seconds=settings.queue_result_ttl_seconds,
    queue_lock_ttl_seconds=settings.queue_lock_ttl_seconds,
    redis_url=settings.redis_url,
    scrape_service=scrape_service,
    query_cache_store=query_cache_store,
)
product_service = ProductService(
    scrape_service=scrape_service,
    search_context_service=search_context_service,
    queue_service=queue_service,
)
account_service = AccountService(product_service)
comparison_service = ComparisonService(
    scrape_service=scrape_service,
    product_service=product_service,
    procurement_service=procurement_service,
    search_context_service=search_context_service,
    queue_service=queue_service,
    offer_verification_service=offer_verification_service,
    decision_service=decision_service,
    candidate_validation_service=candidate_validation_service,
    trusted_vendor_domains=settings.trusted_vendor_domains,
    degraded_source_names=settings.degraded_sources,
)


def configure_services(active_settings: Settings) -> None:
    source_registry.settings = active_settings
    configured_cache_store = QueryCacheStore(active_settings.redis_url)
    scrapers_by_source = source_registry.build_scrapers_by_source()

    scrape_service.configure(
        scrapers_by_source=scrapers_by_source,
        primary_sources=active_settings.primary_sources,
        background_sources=active_settings.background_sources,
        query_cache_store=configured_cache_store,
        cache_ttl_seconds=active_settings.scrape_cache_ttl_seconds,
        background_cache_ttl_seconds=active_settings.background_scrape_cache_ttl_seconds,
        retry_attempts=active_settings.scrape_retry_attempts,
        retry_backoff_seconds=active_settings.scrape_retry_backoff_seconds,
    )
    queue_service.configure(
        queue_backend=active_settings.queue_backend,
        queue_name=active_settings.queue_name,
        queue_job_timeout_seconds=active_settings.queue_job_timeout_seconds,
        queue_result_ttl_seconds=active_settings.queue_result_ttl_seconds,
        queue_lock_ttl_seconds=active_settings.queue_lock_ttl_seconds,
        redis_url=active_settings.redis_url,
        scrape_service=scrape_service,
        query_cache_store=configured_cache_store,
    )
    search_progress_service.configure(active_settings.redis_url)
    offer_verification_service.configure(
        enabled=active_settings.offer_verification_enabled,
        timeout_seconds=active_settings.offer_verification_timeout_seconds,
        cache_ttl_seconds=active_settings.offer_verification_cache_ttl_seconds,
        max_offers=active_settings.offer_verification_max_offers,
        trusted_vendor_domains=active_settings.trusted_vendor_domains,
    )

    candidate_validation_service.configure(
        api_key=active_settings.openrouter_key,
        model=active_settings.openrouter_model,
        enabled=active_settings.llm_validation_enabled and active_settings.environment != "test",
        timeout_seconds=active_settings.llm_validation_timeout_seconds,
        max_candidates=active_settings.llm_validation_max_candidates,
        batch_size=active_settings.llm_validation_batch_size,
        parallel_batches=active_settings.llm_validation_parallel_batches,
    )
    product_service.queue_service = queue_service
    comparison_service.queue_service = queue_service
    comparison_service.trusted_vendor_domains = active_settings.trusted_vendor_domains
    comparison_service.degraded_source_names = tuple(active_settings.degraded_sources)
