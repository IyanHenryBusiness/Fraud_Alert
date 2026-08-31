"""Routes for running the deterministic risk-analysis batch."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.analysis import AnalysisRunResult
from app.services.analysis_service import AnalysisService

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.post("/run", response_model=AnalysisRunResult)
def run_analysis(db: Session = Depends(get_db)) -> AnalysisRunResult:
    """Run the deterministic data-quality and risk-analysis engines and persist alerts."""
    service = AnalysisService(db)
    try:
        return service.run()
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail="Analysis could not be completed."
        ) from exc
