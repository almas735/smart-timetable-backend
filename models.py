"""
Database models for the Smart Timetable app.
------------------------------------------------
Subject.requires_lab and Section.strength are both required -
used by the genetic algorithm for room-type and capacity matching.
"""

from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

engine = create_engine("sqlite:///timetable.db", echo=True)
Base = declarative_base()


class Department(Base):
    __tablename__ = "departments"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)

    faculty = relationship("Faculty", back_populates="department")
    subjects = relationship("Subject", back_populates="department")
    sections = relationship("Section", back_populates="department")


class Faculty(Base):
    __tablename__ = "faculty"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"))

    department = relationship("Department", back_populates="faculty")
    subjects = relationship("Subject", back_populates="faculty")


class Subject(Base):
    __tablename__ = "subjects"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    sessions_per_week = Column(Integer, nullable=False)
    is_elective = Column(Boolean, default=False)
    requires_lab = Column(Boolean, default=False)
    department_id = Column(Integer, ForeignKey("departments.id"))
    faculty_id = Column(Integer, ForeignKey("faculty.id"))

    department = relationship("Department", back_populates="subjects")
    faculty = relationship("Faculty", back_populates="subjects")


class Room(Base):
    __tablename__ = "rooms"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    capacity = Column(Integer, nullable=False)
    room_type = Column(String, nullable=False)


class Section(Base):
    __tablename__ = "sections"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    semester = Column(Integer, nullable=False)
    strength = Column(Integer, nullable=False, default=60)
    department_id = Column(Integer, ForeignKey("departments.id"))

    department = relationship("Department", back_populates="sections")


class TimeSlot(Base):
    __tablename__ = "timeslots"
    id = Column(Integer, primary_key=True)
    day = Column(String, nullable=False)
    period_number = Column(Integer, nullable=False)


class Timetable(Base):
    __tablename__ = "timetables"
    id = Column(Integer, primary_key=True)
    status = Column(String, default="draft")
    created_at = Column(DateTime, default=datetime.utcnow)

    entries = relationship("TimetableEntry", back_populates="timetable")


class TimetableEntry(Base):
    __tablename__ = "timetable_entries"
    id = Column(Integer, primary_key=True)
    timetable_id = Column(Integer, ForeignKey("timetables.id"))
    section_id = Column(Integer, ForeignKey("sections.id"))
    subject_id = Column(Integer, ForeignKey("subjects.id"))
    faculty_id = Column(Integer, ForeignKey("faculty.id"))
    room_id = Column(Integer, ForeignKey("rooms.id"))
    timeslot_id = Column(Integer, ForeignKey("timeslots.id"))

    timetable = relationship("Timetable", back_populates="entries")


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)
    faculty_id = Column(Integer, ForeignKey("faculty.id"), nullable=True)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=True)


if __name__ == "__main__":
    Base.metadata.create_all(engine)
    print("\nDone - timetable.db created with all 9 tables.")
