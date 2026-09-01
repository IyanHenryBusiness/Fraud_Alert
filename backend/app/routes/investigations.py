"""Routes for Phase 5 mock/Gemini investigation generation."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.investigation import InvestigationGenerateRequest, InvestigationResponse
from app.services.copilot_service import (
    AIProviderConfigurationError,
    AIProviderResponseValidationError,
    AIProviderTimeoutError,
    AIProviderUpstreamError,
)
from app.services.investigation_service import (
    AlertNotFoundError,
    InvestigationGenerationError,
    InvestigationService,
)

router = APIRouter(prefix="/api/investigations", tags=["investigations"])


@router.post("/generate", response_model=InvestigationResponse)
def generate_investigation(
    request: InvestigationGenerateRequest,
    db: Session = Depends(get_db),
) -> InvestigationResponse:
    """Generate and persist a new investigation for a single risk alert."""
    try:
        service = InvestigationService(db)
        return service.generate(request.alert_id)
    except AlertNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Alert {request.alert_id} not found"
        )
    except AIProviderConfigurationError:
        raise HTTPException(
            status_code=503, detail="Investigation provider is not configured."
        )
    except AIProviderTimeoutError:
        raise HTTPException(
            status_code=504, detail="Investigation provider timed out."
        )
    except (AIProviderUpstreamError, AIProviderResponseValidationError):
        raise HTTPException(
            status_code=502, detail="Investigation provider request failed."
        )
    except InvestigationGenerationError:
        raise HTTPException(
            status_code=500, detail="Investigation generation failed."
        )
