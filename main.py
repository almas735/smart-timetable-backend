"""
Smart Timetable App - Backend API (complete file)
------------------------------------------------------
Full CRUD for Departments, Faculty, Subjects, Rooms, Sections,
plus timetable generation, retrieval, login, manual override,
and automatic rescheduling for faculty leave.

Run with: uvicorn main:app --reload
Test at:  http://127.0.0.1:8000/docs
"""

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_
from pydantic import BaseModel
import bcrypt

import models
from database import get_db
from scheduler import generate_timetable

app = FastAPI(title="Smart Timetable API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


# ============================================================
# AUTH
# ============================================================

class UserRegister(BaseModel):
    name: str
    email: str
    password: str
    role: str
    faculty_id: int | None = None
    section_id: int | None = None


class UserLogin(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role: str
    faculty_id: int | None
    section_id: int | None

    class Config:
        from_attributes = True


@app.post("/auth/register", response_model=UserOut)
def register(user: UserRegister, db: Session = Depends(get_db)):
    new_user = models.User(
        name=user.name,
        email=user.email,
        password_hash=hash_password(user.password),
        role=user.role,
        faculty_id=user.faculty_id,
        section_id=user.section_id,
    )
    db.add(new_user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="An account with this email already exists.")
    db.refresh(new_user)
    return new_user


@app.post("/auth/login", response_model=UserOut)
def login(credentials: UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == credentials.email).first()
    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return user


# ============================================================
# DEPARTMENTS
# ============================================================

class DepartmentCreate(BaseModel):
    name: str


class DepartmentOut(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


@app.post("/departments", response_model=DepartmentOut)
def create_department(department: DepartmentCreate, db: Session = Depends(get_db)):
    new_dept = models.Department(name=department.name)
    db.add(new_dept)
    db.commit()
    db.refresh(new_dept)
    return new_dept


@app.get("/departments", response_model=list[DepartmentOut])
def list_departments(db: Session = Depends(get_db)):
    return db.query(models.Department).all()


@app.get("/departments/{department_id}", response_model=DepartmentOut)
def get_department(department_id: int, db: Session = Depends(get_db)):
    dept = db.query(models.Department).filter(models.Department.id == department_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    return dept


@app.put("/departments/{department_id}", response_model=DepartmentOut)
def update_department(department_id: int, department: DepartmentCreate, db: Session = Depends(get_db)):
    dept = db.query(models.Department).filter(models.Department.id == department_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    dept.name = department.name
    db.commit()
    db.refresh(dept)
    return dept


@app.delete("/departments/{department_id}")
def delete_department(department_id: int, db: Session = Depends(get_db)):
    dept = db.query(models.Department).filter(models.Department.id == department_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    db.delete(dept)
    db.commit()
    return {"message": f"Department {department_id} deleted"}


# ============================================================
# FACULTY
# ============================================================

class FacultyCreate(BaseModel):
    name: str
    email: str
    department_id: int


class FacultyOut(BaseModel):
    id: int
    name: str
    email: str
    department_id: int

    class Config:
        from_attributes = True


@app.post("/faculty", response_model=FacultyOut)
def create_faculty(faculty: FacultyCreate, db: Session = Depends(get_db)):
    new_faculty = models.Faculty(**faculty.dict())
    db.add(new_faculty)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="A faculty member with this email already exists.")
    db.refresh(new_faculty)
    return new_faculty


@app.get("/faculty", response_model=list[FacultyOut])
def list_faculty(db: Session = Depends(get_db)):
    return db.query(models.Faculty).all()


@app.get("/faculty/{faculty_id}", response_model=FacultyOut)
def get_faculty(faculty_id: int, db: Session = Depends(get_db)):
    faculty = db.query(models.Faculty).filter(models.Faculty.id == faculty_id).first()
    if not faculty:
        raise HTTPException(status_code=404, detail="Faculty not found")
    return faculty


@app.put("/faculty/{faculty_id}", response_model=FacultyOut)
def update_faculty(faculty_id: int, faculty: FacultyCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Faculty).filter(models.Faculty.id == faculty_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Faculty not found")
    for key, value in faculty.dict().items():
        setattr(existing, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="A faculty member with this email already exists.")
    db.refresh(existing)
    return existing


@app.delete("/faculty/{faculty_id}")
def delete_faculty(faculty_id: int, db: Session = Depends(get_db)):
    faculty = db.query(models.Faculty).filter(models.Faculty.id == faculty_id).first()
    if not faculty:
        raise HTTPException(status_code=404, detail="Faculty not found")
    db.delete(faculty)
    db.commit()
    return {"message": f"Faculty {faculty_id} deleted"}


# ============================================================
# SUBJECTS
# ============================================================

class SubjectCreate(BaseModel):
    name: str
    sessions_per_week: int
    is_elective: bool = False
    requires_lab: bool = False
    department_id: int
    faculty_id: int


class SubjectOut(BaseModel):
    id: int
    name: str
    sessions_per_week: int
    is_elective: bool
    requires_lab: bool
    department_id: int
    faculty_id: int

    class Config:
        from_attributes = True


@app.post("/subjects", response_model=SubjectOut)
def create_subject(subject: SubjectCreate, db: Session = Depends(get_db)):
    new_subject = models.Subject(**subject.dict())
    db.add(new_subject)
    db.commit()
    db.refresh(new_subject)
    return new_subject


@app.get("/subjects", response_model=list[SubjectOut])
def list_subjects(db: Session = Depends(get_db)):
    return db.query(models.Subject).all()


@app.get("/subjects/{subject_id}", response_model=SubjectOut)
def get_subject(subject_id: int, db: Session = Depends(get_db)):
    subject = db.query(models.Subject).filter(models.Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    return subject


@app.put("/subjects/{subject_id}", response_model=SubjectOut)
def update_subject(subject_id: int, subject: SubjectCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Subject).filter(models.Subject.id == subject_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Subject not found")
    for key, value in subject.dict().items():
        setattr(existing, key, value)
    db.commit()
    db.refresh(existing)
    return existing


@app.delete("/subjects/{subject_id}")
def delete_subject(subject_id: int, db: Session = Depends(get_db)):
    subject = db.query(models.Subject).filter(models.Subject.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    db.delete(subject)
    db.commit()
    return {"message": f"Subject {subject_id} deleted"}


# ============================================================
# ROOMS
# ============================================================

class RoomCreate(BaseModel):
    name: str
    capacity: int
    room_type: str


class RoomOut(BaseModel):
    id: int
    name: str
    capacity: int
    room_type: str

    class Config:
        from_attributes = True


@app.post("/rooms", response_model=RoomOut)
def create_room(room: RoomCreate, db: Session = Depends(get_db)):
    new_room = models.Room(**room.dict())
    db.add(new_room)
    db.commit()
    db.refresh(new_room)
    return new_room


@app.get("/rooms", response_model=list[RoomOut])
def list_rooms(db: Session = Depends(get_db)):
    return db.query(models.Room).all()


@app.get("/rooms/{room_id}", response_model=RoomOut)
def get_room(room_id: int, db: Session = Depends(get_db)):
    room = db.query(models.Room).filter(models.Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return room


@app.put("/rooms/{room_id}", response_model=RoomOut)
def update_room(room_id: int, room: RoomCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Room).filter(models.Room.id == room_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Room not found")
    for key, value in room.dict().items():
        setattr(existing, key, value)
    db.commit()
    db.refresh(existing)
    return existing


@app.delete("/rooms/{room_id}")
def delete_room(room_id: int, db: Session = Depends(get_db)):
    room = db.query(models.Room).filter(models.Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    db.delete(room)
    db.commit()
    return {"message": f"Room {room_id} deleted"}


# ============================================================
# SECTIONS
# ============================================================

class SectionCreate(BaseModel):
    name: str
    semester: int
    strength: int
    department_id: int


class SectionOut(BaseModel):
    id: int
    name: str
    semester: int
    strength: int
    department_id: int

    class Config:
        from_attributes = True


@app.post("/sections", response_model=SectionOut)
def create_section(section: SectionCreate, db: Session = Depends(get_db)):
    new_section = models.Section(**section.dict())
    db.add(new_section)
    db.commit()
    db.refresh(new_section)
    return new_section


@app.get("/sections", response_model=list[SectionOut])
def list_sections(db: Session = Depends(get_db)):
    return db.query(models.Section).all()


@app.get("/sections/{section_id}", response_model=SectionOut)
def get_section(section_id: int, db: Session = Depends(get_db)):
    section = db.query(models.Section).filter(models.Section.id == section_id).first()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    return section


@app.put("/sections/{section_id}", response_model=SectionOut)
def update_section(section_id: int, section: SectionCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Section).filter(models.Section.id == section_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Section not found")
    for key, value in section.dict().items():
        setattr(existing, key, value)
    db.commit()
    db.refresh(existing)
    return existing


@app.delete("/sections/{section_id}")
def delete_section(section_id: int, db: Session = Depends(get_db)):
    section = db.query(models.Section).filter(models.Section.id == section_id).first()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    db.delete(section)
    db.commit()
    return {"message": f"Section {section_id} deleted"}


# ============================================================
# TIMETABLE GENERATION
# ============================================================

@app.post("/timetable/generate")
def create_timetable(db: Session = Depends(get_db)):
    try:
        assignments, metrics = generate_timetable(db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    new_timetable = models.Timetable(status="draft")
    db.add(new_timetable)
    db.commit()
    db.refresh(new_timetable)

    existing_slots = {(t.day, t.period_number): t.id for t in db.query(models.TimeSlot).all()}
    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    periods_per_day = 6
    if len(existing_slots) < len(days) * periods_per_day:
        for day in days:
            for p in range(1, periods_per_day + 1):
                if (day, p) not in existing_slots:
                    db.add(models.TimeSlot(day=day, period_number=p))
        db.commit()
        existing_slots = {(t.day, t.period_number): t.id for t in db.query(models.TimeSlot).all()}

    for a in assignments:
        day_index = a["timeslot"] // periods_per_day
        period = a["timeslot"] % periods_per_day + 1
        timeslot_id = existing_slots[(days[day_index], period)]

        db.add(models.TimetableEntry(
            timetable_id=new_timetable.id,
            section_id=a["section_id"],
            subject_id=a["subject_id"],
            faculty_id=a["faculty_id"],
            room_id=a["room_id"],
            timeslot_id=timeslot_id,
        ))
    db.commit()

    return {
        "timetable_id": new_timetable.id,
        "status": new_timetable.status,
        "metrics": metrics,
        "total_entries": len(assignments),
    }


@app.get("/timetable/latest")
def get_latest_timetable(db: Session = Depends(get_db)):
    timetable = db.query(models.Timetable).order_by(models.Timetable.id.desc()).first()
    if not timetable:
        raise HTTPException(status_code=404, detail="No timetable has been generated yet")
    return get_timetable(timetable.id, db)


@app.get("/timetable/{timetable_id}")
def get_timetable(timetable_id: int, db: Session = Depends(get_db)):
    timetable = db.query(models.Timetable).filter(models.Timetable.id == timetable_id).first()
    if not timetable:
        raise HTTPException(status_code=404, detail="Timetable not found")

    entries = db.query(models.TimetableEntry).filter(models.TimetableEntry.timetable_id == timetable_id).all()
    result = []
    for e in entries:
        slot = db.query(models.TimeSlot).filter(models.TimeSlot.id == e.timeslot_id).first()
        section = db.query(models.Section).filter(models.Section.id == e.section_id).first()
        subject = db.query(models.Subject).filter(models.Subject.id == e.subject_id).first()
        faculty = db.query(models.Faculty).filter(models.Faculty.id == e.faculty_id).first()
        room = db.query(models.Room).filter(models.Room.id == e.room_id).first()
        result.append({
            "entry_id": e.id,
            "section": section.name,
            "section_id": e.section_id,
            "subject": subject.name,
            "subject_id": e.subject_id,
            "faculty": faculty.name,
            "faculty_id": e.faculty_id,
            "room": room.name,
            "room_id": e.room_id,
            "day": slot.day,
            "period": slot.period_number,
        })

    return {"timetable_id": timetable_id, "status": timetable.status, "entries": result}


class TimetableEntryUpdate(BaseModel):
    day: str
    period: int
    room_id: int


@app.put("/timetable/entries/{entry_id}")
def update_timetable_entry(entry_id: int, update: TimetableEntryUpdate, db: Session = Depends(get_db)):
    entry = db.query(models.TimetableEntry).filter(models.TimetableEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Timetable entry not found")

    slot = db.query(models.TimeSlot).filter(
        models.TimeSlot.day == update.day,
        models.TimeSlot.period_number == update.period,
    ).first()
    if not slot:
        raise HTTPException(status_code=400, detail="Invalid day/period")

    conflicting = db.query(models.TimetableEntry).filter(
        models.TimetableEntry.timetable_id == entry.timetable_id,
        models.TimetableEntry.timeslot_id == slot.id,
        models.TimetableEntry.id != entry.id,
    ).filter(
        or_(
            models.TimetableEntry.section_id == entry.section_id,
            models.TimetableEntry.faculty_id == entry.faculty_id,
            models.TimetableEntry.room_id == update.room_id,
        )
    ).first()

    if conflicting:
        raise HTTPException(
            status_code=400,
            detail="This move would create a clash - that section, faculty, or room is already booked at this time.",
        )

    room = db.query(models.Room).filter(models.Room.id == update.room_id).first()
    subject = db.query(models.Subject).filter(models.Subject.id == entry.subject_id).first()
    section = db.query(models.Section).filter(models.Section.id == entry.section_id).first()
    if not room or not subject or not section:
        raise HTTPException(status_code=400, detail="Invalid data")
    if subject.requires_lab and room.room_type != "lab":
        raise HTTPException(status_code=400, detail="This subject requires a lab room.")
    if room.capacity < section.strength:
        raise HTTPException(status_code=400, detail="This room is too small for this section.")

    entry.timeslot_id = slot.id
    entry.room_id = update.room_id
    db.commit()
    return {"message": "Moved successfully"}


class LeaveRequest(BaseModel):
    faculty_id: int
    day: str


@app.post("/timetable/reschedule-leave")
def reschedule_for_leave(request: LeaveRequest, db: Session = Depends(get_db)):
    timetable = db.query(models.Timetable).order_by(models.Timetable.id.desc()).first()
    if not timetable:
        raise HTTPException(status_code=404, detail="No timetable has been generated yet")

    affected_entries = (
        db.query(models.TimetableEntry)
        .join(models.TimeSlot, models.TimetableEntry.timeslot_id == models.TimeSlot.id)
        .filter(
            models.TimetableEntry.timetable_id == timetable.id,
            models.TimetableEntry.faculty_id == request.faculty_id,
            models.TimeSlot.day == request.day,
        )
        .all()
    )

    if not affected_entries:
        return {
            "message": "This faculty member has no classes on that day - nothing to reschedule.",
            "moved": [],
            "unresolved": [],
        }

    all_timeslots = db.query(models.TimeSlot).all()
    all_rooms = db.query(models.Room).all()
    all_entries_in_timetable = db.query(models.TimetableEntry).filter(
        models.TimetableEntry.timetable_id == timetable.id
    ).all()
    slot_lookup = {t.id: t for t in all_timeslots}

    moved = []
    unresolved = []

    for entry in affected_entries:
        subject = db.query(models.Subject).filter(models.Subject.id == entry.subject_id).first()
        section = db.query(models.Section).filter(models.Section.id == entry.section_id).first()

        valid_rooms = [
            r for r in all_rooms
            if (r.room_type == "lab") == subject.requires_lab and r.capacity >= section.strength
        ]

        old_slot = slot_lookup[entry.timeslot_id]
        found = False

        for slot in all_timeslots:
            if slot.day == request.day:
                continue
            for room in valid_rooms:
                conflict = any(
                    other.id != entry.id and other.timeslot_id == slot.id and (
                        other.section_id == entry.section_id or
                        other.faculty_id == entry.faculty_id or
                        other.room_id == room.id
                    )
                    for other in all_entries_in_timetable
                )
                if not conflict:
                    entry.timeslot_id = slot.id
                    entry.room_id = room.id
                    moved.append({
                        "subject": subject.name,
                        "section": section.name,
                        "from_day": old_slot.day,
                        "from_period": old_slot.period_number,
                        "to_day": slot.day,
                        "to_period": slot.period_number,
                        "room": room.name,
                    })
                    found = True
                    break
            if found:
                break

        if not found:
            unresolved.append({"subject": subject.name, "section": section.name})

    db.commit()

    return {
        "message": f"Rescheduled {len(moved)} of {len(affected_entries)} affected class(es).",
        "moved": moved,
        "unresolved": unresolved,
    }
