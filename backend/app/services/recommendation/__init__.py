from app.services.recommendation.service import UnifiedRecommendationService

# Canonical recommendation engine entry point. The former
# ``HybridRecommendationService`` (a duplicate standalone algorithm) has been
# removed in favour of a single engine; see hybrid.py for the deprecation guard.
__all__ = ["UnifiedRecommendationService"]
