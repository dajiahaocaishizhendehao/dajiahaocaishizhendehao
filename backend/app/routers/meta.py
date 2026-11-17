"""基础资料：代理机构、项目、权利人、人员。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_write
from app.models import Agency, Party, Person, Project, User
from app.schemas import (
    AgencyIn,
    AgencyOut,
    Page,
    PartyIn,
    PartyOut,
    PersonIn,
    PersonOut,
    ProjectIn,
    ProjectOut,
)
from app.services import paginate, write_audit

router = APIRouter(tags=["基础资料"])


@router.get("/agencies", response_model=Page[AgencyOut])
def list_agencies(
    q: str | None = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Page[AgencyOut]:
    stmt = select(Agency).where(Agency.is_deleted.is_(False))
    if q:
        stmt = stmt.where(or_(Agency.name.ilike(f"%{q}%"), Agency.contact.ilike(f"%{q}%")))
    rows, total = paginate(db, stmt.order_by(Agency.name), page=page, page_size=page_size)
    return Page[AgencyOut](
        items=[AgencyOut.model_validate(item) for item in rows], total=total, page=page, page_size=page_size
    )


@router.post("/agencies", response_model=AgencyOut, status_code=status.HTTP_201_CREATED)
def create_agency(
    payload: AgencyIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
) -> AgencyOut:
    agency = Agency(**payload.model_dump(), created_by=user.id, updated_by=user.id)
    db.add(agency)
    write_audit(
        db,
        user=user,
        action="create",
        object_type="agency",
        object_id=agency.id,
        summary=agency.name,
        request=request,
    )
    db.commit()
    return AgencyOut.model_validate(agency)


@router.get("/projects", response_model=Page[ProjectOut])
def list_projects(
    q: str | None = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Page[ProjectOut]:
    stmt = select(Project).where(Project.is_deleted.is_(False))
    if q:
        stmt = stmt.where(or_(Project.name.ilike(f"%{q}%"), Project.code.ilike(f"%{q}%")))
    rows, total = paginate(db, stmt.order_by(Project.name), page=page, page_size=page_size)
    return Page[ProjectOut](
        items=[ProjectOut.model_validate(item) for item in rows], total=total, page=page, page_size=page_size
    )


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
) -> ProjectOut:
    if payload.code and db.scalar(
        select(Project.id).where(Project.code == payload.code, Project.is_deleted.is_(False))
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="项目编码已存在")
    project = Project(**payload.model_dump(), created_by=user.id, updated_by=user.id)
    db.add(project)
    write_audit(
        db,
        user=user,
        action="create",
        object_type="project",
        object_id=project.id,
        summary=project.name,
        request=request,
    )
    db.commit()
    db.refresh(project)
    return ProjectOut.model_validate(project)


@router.get("/parties", response_model=Page[PartyOut])
def list_parties(
    q: str | None = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Page[PartyOut]:
    stmt = select(Party).where(Party.is_deleted.is_(False))
    if q:
        stmt = stmt.where(Party.name.ilike(f"%{q}%"))
    rows, total = paginate(db, stmt.order_by(Party.name), page=page, page_size=page_size)
    return Page[PartyOut](
        items=[PartyOut.model_validate(item) for item in rows], total=total, page=page, page_size=page_size
    )


@router.post("/parties", response_model=PartyOut, status_code=status.HTTP_201_CREATED)
def create_party(
    payload: PartyIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
) -> PartyOut:
    party = Party(**payload.model_dump(), created_by=user.id, updated_by=user.id)
    db.add(party)
    write_audit(
        db,
        user=user,
        action="create",
        object_type="party",
        object_id=party.id,
        summary=party.name,
        request=request,
    )
    db.commit()
    return PartyOut.model_validate(party)


@router.patch("/parties/{party_id}", response_model=PartyOut)
def update_party(
    party_id: str,
    payload: PartyIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
) -> PartyOut:
    party = db.get(Party, party_id)
    if party is None or party.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="权利人不存在")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(party, field, value)
    party.updated_by = user.id
    write_audit(
        db,
        user=user,
        action="update",
        object_type="party",
        object_id=party.id,
        summary=party.name,
        request=request,
    )
    db.commit()
    return PartyOut.model_validate(party)


@router.delete("/parties/{party_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_party(
    party_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
) -> None:
    party = db.get(Party, party_id)
    if party is None or party.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="权利人不存在")

    party.is_deleted = True
    party.updated_by = user.id
    write_audit(
        db,
        user=user,
        action="delete",
        object_type="party",
        object_id=party.id,
        summary=party.name,
        request=request,
    )
    db.commit()


@router.patch("/agencies/{agency_id}", response_model=AgencyOut)
def update_agency(
    agency_id: str,
    payload: AgencyIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
) -> AgencyOut:
    agency = db.get(Agency, agency_id)
    if agency is None or agency.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="代理机构不存在")

    for field, value in payload.model_dump().items():
        setattr(agency, field, value)
    agency.updated_by = user.id
    write_audit(
        db,
        user=user,
        action="update",
        object_type="agency",
        object_id=agency.id,
        summary=agency.name,
        request=request,
    )
    db.commit()
    return AgencyOut.model_validate(agency)


@router.delete("/agencies/{agency_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_agency(
    agency_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
) -> None:
    agency = db.get(Agency, agency_id)
    if agency is None or agency.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="代理机构不存在")

    agency.is_deleted = True
    agency.updated_by = user.id
    write_audit(
        db,
        user=user,
        action="delete",
        object_type="agency",
        object_id=agency.id,
        summary=agency.name,
        request=request,
    )
    db.commit()


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: str,
    payload: ProjectIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
) -> ProjectOut:
    project = db.get(Project, project_id)
    if project is None or project.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")

    if payload.code and db.scalar(
        select(Project.id).where(
            Project.code == payload.code,
            Project.id != project_id,
            Project.is_deleted.is_(False),
        )
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="项目编码已存在")

    for field, value in payload.model_dump().items():
        setattr(project, field, value)
    project.updated_by = user.id
    write_audit(
        db,
        user=user,
        action="update",
        object_type="project",
        object_id=project.id,
        summary=project.name,
        request=request,
    )
    db.commit()
    db.refresh(project)
    return ProjectOut.model_validate(project)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_project(
    project_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
) -> None:
    project = db.get(Project, project_id)
    if project is None or project.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")

    project.is_deleted = True
    project.updated_by = user.id
    write_audit(
        db,
        user=user,
        action="delete",
        object_type="project",
        object_id=project.id,
        summary=project.name,
        request=request,
    )
    db.commit()


@router.get("/persons", response_model=Page[PersonOut])
def list_persons(
    q: str | None = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Page[PersonOut]:
    stmt = select(Person).where(Person.is_deleted.is_(False))
    if q:
        stmt = stmt.where(or_(Person.name.ilike(f"%{q}%"), Person.employee_no.ilike(f"%{q}%")))
    rows, total = paginate(db, stmt.order_by(Person.name), page=page, page_size=page_size)
    return Page[PersonOut](
        items=[PersonOut.model_validate(item) for item in rows], total=total, page=page, page_size=page_size
    )


@router.post("/persons", response_model=PersonOut, status_code=status.HTTP_201_CREATED)
def create_person(
    payload: PersonIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_write),
) -> PersonOut:
    person = Person(**payload.model_dump(), created_by=user.id, updated_by=user.id)
    db.add(person)
    write_audit(
        db,
        user=user,
        action="create",
        object_type="person",
        object_id=person.id,
        summary=person.name,
        request=request,
    )
    db.commit()
    return PersonOut.model_validate(person)
