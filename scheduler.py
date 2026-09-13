"""
Wraps the genetic algorithm + repair logic into a reusable function
the backend API can call on demand.
"""

import pygad
from sqlalchemy.orm import Session
import models

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
PERIODS_PER_DAY = 6
TOTAL_SLOTS = len(DAYS) * PERIODS_PER_DAY


def generate_timetable(db: Session):
    """Runs the full pipeline (load data -> GA -> repair) and
    returns (assignments, metrics). Raises ValueError if there's
    no data to schedule yet."""

    sections = db.query(models.Section).all()
    rooms = db.query(models.Room).all()

    if not sections or not rooms:
        raise ValueError("No sections or rooms found - add data first.")

    sessions_to_schedule = []
    for section in sections:
        subjects = db.query(models.Subject).filter(
            models.Subject.department_id == section.department_id
        ).all()
        for subject in subjects:
            for _ in range(subject.sessions_per_week):
                sessions_to_schedule.append({
                    "section_id": section.id,
                    "subject_id": subject.id,
                    "faculty_id": subject.faculty_id,
                    "section_strength": section.strength,
                    "requires_lab": subject.requires_lab,
                })

    num_sessions = len(sessions_to_schedule)
    print(f"[scheduler] Starting generation: {len(sections)} sections, "
          f"{num_sessions} sessions to schedule. This takes 4-7 minutes - "
          f"please wait, this is not stuck.")

    def valid_room_indices(session):
        matches = [
            idx for idx, room in enumerate(rooms)
            if (room.room_type == "lab") == session["requires_lab"]
            and room.capacity >= session["section_strength"]
        ]
        return matches if matches else list(range(len(rooms)))

    num_genes = num_sessions * 2
    gene_space = []
    for sess in sessions_to_schedule:
        gene_space.append(list(range(TOTAL_SLOTS)))
        gene_space.append(valid_room_indices(sess))

    def decode(solution):
        assignments = []
        for i, sess in enumerate(sessions_to_schedule):
            timeslot = int(solution[i * 2])
            room_idx = int(solution[i * 2 + 1])
            room = rooms[room_idx]
            assignments.append({
                **sess,
                "timeslot": timeslot,
                "room_id": room.id,
                "room_type": room.room_type,
                "room_capacity": room.capacity,
            })
        return assignments

    def analyze(assignments):
        section_slot, faculty_slot, room_slot, subject_day = {}, {}, {}, {}
        for a in assignments:
            day_index = a["timeslot"] // PERIODS_PER_DAY
            section_slot[(a["section_id"], a["timeslot"])] = section_slot.get((a["section_id"], a["timeslot"]), 0) + 1
            faculty_slot[(a["faculty_id"], a["timeslot"])] = faculty_slot.get((a["faculty_id"], a["timeslot"]), 0) + 1
            room_slot[(a["room_id"], a["timeslot"])] = room_slot.get((a["room_id"], a["timeslot"]), 0) + 1
            key = (a["section_id"], a["subject_id"], day_index)
            subject_day[key] = subject_day.get(key, 0) + 1

        return {
            "section_conflicts": sum(c - 1 for c in section_slot.values() if c > 1),
            "faculty_conflicts": sum(c - 1 for c in faculty_slot.values() if c > 1),
            "room_conflicts": sum(c - 1 for c in room_slot.values() if c > 1),
            "lab_mismatches": sum(1 for a in assignments if a["requires_lab"] != (a["room_type"] == "lab")),
            "capacity_issues": sum(1 for a in assignments if a["room_capacity"] < a["section_strength"]),
            "same_day_repeats": sum(c - 1 for c in subject_day.values() if c > 1),
        }

    def fitness_func(ga_instance, solution, solution_idx):
        m = analyze(decode(solution))
        penalty = (
            m["section_conflicts"] * 20 +
            m["faculty_conflicts"] * 20 +
            m["room_conflicts"] * 20 +
            m["lab_mismatches"] * 15 +
            m["capacity_issues"] * 15 +
            m["same_day_repeats"] * 15
        )
        return 1 / (1 + penalty)

    ga_instance = pygad.GA(
        num_generations=1800,
        num_parents_mating=20,
        fitness_func=fitness_func,
        sol_per_pop=180,
        num_genes=num_genes,
        gene_space=gene_space,
        parent_selection_type="sss",
        keep_elitism=12,
        crossover_type="single_point",
        mutation_type="random",
        mutation_percent_genes=15,
    )
    ga_instance.run()
    print("[scheduler] Genetic algorithm finished, running repair step...")
    best_solution, _, _ = ga_instance.best_solution()
    assignments = decode(best_solution)

    def find_conflicting_indices(assignments):
        section_slot, faculty_slot, room_slot = {}, {}, {}
        for i, a in enumerate(assignments):
            section_slot.setdefault((a["section_id"], a["timeslot"]), []).append(i)
            faculty_slot.setdefault((a["faculty_id"], a["timeslot"]), []).append(i)
            room_slot.setdefault((a["room_id"], a["timeslot"]), []).append(i)
        conflicting = set()
        for group in list(section_slot.values()) + list(faculty_slot.values()) + list(room_slot.values()):
            if len(group) > 1:
                conflicting.update(group[1:])
        return conflicting

    def slot_is_free_for(assignments, idx, timeslot, room):
        a = assignments[idx]
        for j, other in enumerate(assignments):
            if j == idx or other["timeslot"] != timeslot:
                continue
            if other["section_id"] == a["section_id"]:
                return False
            if other["faculty_id"] == a["faculty_id"]:
                return False
            if other["room_id"] == room.id:
                return False
        return True

    conflicting = find_conflicting_indices(assignments)
    rounds = 0
    while conflicting and rounds < 300:
        idx = conflicting.pop()
        a = assignments[idx]
        candidate_rooms = [rooms[i] for i in valid_room_indices(a)]
        for ts in range(TOTAL_SLOTS):
            fixed = False
            for room in candidate_rooms:
                if slot_is_free_for(assignments, idx, ts, room):
                    assignments[idx].update({
                        "timeslot": ts,
                        "room_id": room.id,
                        "room_type": room.room_type,
                        "room_capacity": room.capacity,
                    })
                    fixed = True
                    break
            if fixed:
                break
        rounds += 1
        conflicting = find_conflicting_indices(assignments)

    metrics = analyze(assignments)
    print(f"[scheduler] Done. Hard conflicts: "
          f"{metrics['section_conflicts'] + metrics['faculty_conflicts'] + metrics['room_conflicts']}")
    return assignments, metrics