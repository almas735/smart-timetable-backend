"""
Seed script - EXPANDED version for scalability testing.
Now includes a 3rd department (Mechanical) to scale from
3 sections/55 sessions up to 5 sections/~83 sessions - a
meaningful stress test for your report's results section.
Safe to re-run any time - it clears old data first.
"""

import bcrypt
from database import SessionLocal
import models


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


db = SessionLocal()

db.query(models.User).delete()
db.query(models.TimetableEntry).delete()
db.query(models.Timetable).delete()
db.query(models.Subject).delete()
db.query(models.Section).delete()
db.query(models.Faculty).delete()
db.query(models.Room).delete()
db.query(models.Department).delete()
db.commit()

cs = models.Department(name="Computer Science")
ece = models.Department(name="Electronics")
mech = models.Department(name="Mechanical Engineering")
db.add_all([cs, ece, mech])
db.commit()

sharma = models.Faculty(name="Prof. Sharma", email="sharma@college.edu", department_id=cs.id)
verma = models.Faculty(name="Prof. Verma", email="verma@college.edu", department_id=cs.id)
iyer = models.Faculty(name="Prof. Iyer", email="iyer@college.edu", department_id=cs.id)
singh = models.Faculty(name="Prof. Singh", email="singh@college.edu", department_id=cs.id)
rao = models.Faculty(name="Prof. Rao", email="rao@college.edu", department_id=ece.id)
nair = models.Faculty(name="Prof. Nair", email="nair@college.edu", department_id=ece.id)
gupta = models.Faculty(name="Prof. Gupta", email="gupta@college.edu", department_id=mech.id)
reddy = models.Faculty(name="Prof. Reddy", email="reddy@college.edu", department_id=mech.id)
kumar = models.Faculty(name="Prof. Kumar", email="kumar@college.edu", department_id=mech.id)
db.add_all([sharma, verma, iyer, singh, rao, nair, gupta, reddy, kumar])
db.commit()

subjects = [
    models.Subject(name="Data Structures", sessions_per_week=5, requires_lab=False, department_id=cs.id, faculty_id=sharma.id),
    models.Subject(name="Operating Systems", sessions_per_week=5, requires_lab=False, department_id=cs.id, faculty_id=verma.id),
    models.Subject(name="Database Systems", sessions_per_week=4, requires_lab=False, department_id=cs.id, faculty_id=iyer.id),
    models.Subject(name="Software Engineering", sessions_per_week=3, requires_lab=False, department_id=cs.id, faculty_id=singh.id),
    models.Subject(name="Programming Lab", sessions_per_week=3, requires_lab=True, department_id=cs.id, faculty_id=sharma.id),
    models.Subject(name="Digital Electronics", sessions_per_week=4, requires_lab=False, department_id=ece.id, faculty_id=rao.id),
    models.Subject(name="Signals and Systems", sessions_per_week=4, requires_lab=False, department_id=ece.id, faculty_id=nair.id),
    models.Subject(name="Microprocessors", sessions_per_week=4, requires_lab=False, department_id=ece.id, faculty_id=rao.id),
    models.Subject(name="Electronics Lab", sessions_per_week=3, requires_lab=True, department_id=ece.id, faculty_id=nair.id),
    models.Subject(name="Thermodynamics", sessions_per_week=4, requires_lab=False, department_id=mech.id, faculty_id=gupta.id),
    models.Subject(name="Fluid Mechanics", sessions_per_week=4, requires_lab=False, department_id=mech.id, faculty_id=reddy.id),
    models.Subject(name="Machine Design", sessions_per_week=3, requires_lab=False, department_id=mech.id, faculty_id=kumar.id),
    models.Subject(name="Manufacturing Lab", sessions_per_week=3, requires_lab=True, department_id=mech.id, faculty_id=gupta.id),
]
db.add_all(subjects)
db.commit()

rooms = [
    models.Room(name="Room 101", capacity=70, room_type="classroom"),
    models.Room(name="Room 102", capacity=70, room_type="classroom"),
    models.Room(name="Room 201", capacity=60, room_type="classroom"),
    models.Room(name="Room 301", capacity=65, room_type="classroom"),
    models.Room(name="CS Lab", capacity=65, room_type="lab"),
    models.Room(name="ECE Lab", capacity=60, room_type="lab"),
    models.Room(name="Mech Lab", capacity=55, room_type="lab"),
]
db.add_all(rooms)
db.commit()

sections = [
    models.Section(name="CSE-3A", semester=5, strength=55, department_id=cs.id),
    models.Section(name="CSE-3B", semester=5, strength=58, department_id=cs.id),
    models.Section(name="ECE-3A", semester=5, strength=50, department_id=ece.id),
    models.Section(name="MECH-3A", semester=5, strength=52, department_id=mech.id),
    models.Section(name="MECH-3B", semester=5, strength=50, department_id=mech.id),
]
db.add_all(sections)
db.commit()

admin_user = models.User(
    name="Admin User",
    email="admin@college.edu",
    password_hash=hash_password("admin123"),
    role="admin",
)

faculty_user = models.User(
    name="Prof. Sharma",
    email="sharma.login@college.edu",
    password_hash=hash_password("faculty123"),
    role="faculty",
    faculty_id=sharma.id,
)

student_user = models.User(
    name="Student (CSE-3A)",
    email="student@college.edu",
    password_hash=hash_password("student123"),
    role="student",
    section_id=sections[0].id,
)

db.add_all([admin_user, faculty_user, student_user])
db.commit()
db.close()

print("Seed data inserted: 3 departments, 9 faculty, 13 subjects, 7 rooms, 5 sections")
print("")
print("=== Demo login accounts ===")
print("Admin:   admin@college.edu   / admin123")
print("Faculty: sharma.login@college.edu / faculty123   (this is Prof. Sharma)")
print("Student: student@college.edu / student123   (this is CSE-3A)")
