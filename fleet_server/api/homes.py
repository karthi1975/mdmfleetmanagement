"""Home CRUD endpoints with community assignment."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_server.database import get_db
from fleet_server.repositories.home import HomeRepository
from fleet_server.schemas.community import CommunityResponse
from fleet_server.schemas.home import HomeCreate, HomeResponse, HomeUpdate, HomeWithCommunitiesResponse

router = APIRouter()


def get_repo(db: AsyncSession = Depends(get_db)) -> HomeRepository:
    return HomeRepository(db)


@router.get("/", response_model=list[HomeResponse])
async def list_homes(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    repo: HomeRepository = Depends(get_repo),
):
    return await repo.get_all(skip=skip, limit=limit)


@router.get("/{home_id}", response_model=HomeWithCommunitiesResponse)
async def get_home(
    home_id: str,
    repo: HomeRepository = Depends(get_repo),
):
    home = await repo.get_with_communities(home_id)
    if not home:
        raise HTTPException(status_code=404, detail="Home not found")
    return home


@router.post("/", response_model=HomeResponse, status_code=201)
async def create_home(
    payload: HomeCreate,
    repo: HomeRepository = Depends(get_repo),
):
    existing = await repo.get_by_id(payload.home_id)
    if existing:
        raise HTTPException(status_code=409, detail="Home already exists")
    return await repo.create(payload.model_dump())


@router.patch("/{home_id}", response_model=HomeResponse)
async def update_home(
    home_id: str,
    payload: HomeUpdate,
    repo: HomeRepository = Depends(get_repo),
):
    home = await repo.update(home_id, payload.model_dump(exclude_unset=True))
    if not home:
        raise HTTPException(status_code=404, detail="Home not found")
    return home


@router.delete("/{home_id}", status_code=204)
async def delete_home(
    home_id: str,
    repo: HomeRepository = Depends(get_repo),
):
    deleted = await repo.delete(home_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Home not found")


@router.post("/{home_id}/communities/{community_id}", status_code=201)
async def assign_community(
    home_id: str,
    community_id: str,
    repo: HomeRepository = Depends(get_repo),
):
    success = await repo.assign_community(home_id, community_id)
    if not success:
        raise HTTPException(status_code=404, detail="Home or community not found")
    return {"message": f"Community {community_id} assigned to home {home_id}"}


@router.delete("/{home_id}/communities/{community_id}", status_code=204)
async def remove_community(
    home_id: str,
    community_id: str,
    repo: HomeRepository = Depends(get_repo),
):
    removed = await repo.remove_community(home_id, community_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Assignment not found")


@router.get("/{home_id}/communities", response_model=list[CommunityResponse])
async def list_home_communities(
    home_id: str,
    repo: HomeRepository = Depends(get_repo),
):
    home = await repo.get_with_communities(home_id)
    if not home:
        raise HTTPException(status_code=404, detail="Home not found")
    return home.communities
