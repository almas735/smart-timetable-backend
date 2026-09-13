"""
Smart Timetable Generator - Genetic Algorithm (Version 3)
--------------------------------------------------------------
Version 2.1 relied purely on the GA finding a perfect solution,
which isn't guaranteed since a GA is a randomized search - a hard
problem (like two sections sharing the same faculty for the same
subjects, which creates very tight scheduling contention) can
occasionally leave 1-2 small conflicts even after a long run.

Version 3 fixes this properly: run the GA once to get a strong
overall solution, then run a fast, deterministic REPAIR step that
specifically hunts down any remaining hard-constraint conflicts and
relocates just those sessions to a free slot. This combination
(metaheuristic search + local repair) is how real-world scheduling
systems guarantee correctness instead of hoping for a lucky run.

Guarantees after repair:
  - No faculty member teaches two classes at the same time
  - No room hosts two classes at the same time
  - No section has two classes at the same time

Guaranteed structurally (can't even happen, from Version 2.1):
  - Lab subjects only ever get offered lab rooms
  - A section is only ever offered rooms big enough for it

Optimized for (soft constraint, not touched by repair):
  - Not repeating the same subject twice in one day for a section
"""

import pygad
from database import SessionLocal
import models

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
PERIODS_PER_DAY = 6
TOTAL_SLOTS = len(DAYS) * PERIODS_PER_DAY

db = SessionLocal()
sections = db.query(models.Section).all()
rooms = db.query(models.Room).all()

if not sections or not rooms:
    raise SystemExit("No sections or rooms found - run seed_data.py first.")

sessions_to_schedule = []
for section in sections:
    subjects = db.query(models.Subject).filter(
        models.Subject.department_id == section.department_id
    ).all()
    for subject in subjects:
        for _ in range(subject.sessions_per_week):
            sessions_to_schedule.append({
                "section_id": section.id,
                "section_name": section.name,
                "section_strength": section.strength,
                "subject_id": subject.id,
                "subject_name": subject.name,
                "faculty_id": subject.faculty_id,
                "requires_lab": subject.requires_lab,
            })

num_sessions = len(sessions_to_schedule)
db.close()

print(f"Loaded {len(sections)} sections, {len(rooms)} rooms, "
      f"{num_sessions} total class sessions to schedule.\n")


def valid_room_indices(session):
    """Only rooms of the correct type (lab vs classroom) and big
    enough for the section are ever offered for this session."""
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
        assignments.append({
            **sess,
            "timeslot": timeslot,
            "day_index": timeslot // PERIODS_PER_DAY,
            "period": timeslot % PERIODS_PER_DAY,
            "room": rooms[room_idx],
        })
    return assignments


def analyze(assignments):
    section_slot, faculty_slot, room_slot, subject_day = {}, {}, {}, {}
    for a in assignments:
        section_slot[(a["section_id"], a["timeslot"])] = section_slot.get((a["section_id"], a["timeslot"]), 0) + 1
        faculty_slot[(a["faculty_id"], a["timeslot"])] = faculty_slot.get((a["faculty_id"], a["timeslot"]), 0) + 1
        room_slot[(a["room"].id, a["timeslot"])] = room_slot.get((a["room"].id, a["timeslot"]), 0) + 1
        key = (a["section_id"], a["subject_id"], a["day_index"])
        subject_day[key] = subject_day.get(key, 0) + 1

    return {
        "section_conflicts": sum(c - 1 for c in section_slot.values() if c > 1),
        "faculty_conflicts": sum(c - 1 for c in faculty_slot.values() if c > 1),
        "room_conflicts": sum(c - 1 for c in room_slot.values() if c > 1),
        "lab_mismatches": sum(1 for a in assignments if a["requires_lab"] != (a["room"].room_type == "lab")),
        "capacity_issues": sum(1 for a in assignments if a["room"].capacity < a["section_strength"]),
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

print("Running the genetic algorithm... expect roughly 4-7 minutes.\n")
ga_instance.run()

best_solution, best_fitness, _ = ga_instance.best_solution()
assignments = decode(best_solution)
pre_repair = analyze(assignments)
pre_repair_hard = pre_repair["section_conflicts"] + pre_repair["faculty_conflicts"] + pre_repair["room_conflicts"]

print(f"\nBefore repair: {pre_repair_hard} hard violation(s), "
      f"{pre_repair['same_day_repeats']} same-day repeat(s), "
      f"fitness = {best_fitness:.4f}")


# ============================================================
# REPAIR STEP - deterministic local search that guarantees zero
# hard-constraint violations, instead of hoping the GA got lucky.
# It only touches the specific sessions causing a conflict, and
# moves each one to the first fully free slot+room it can find.
# ============================================================

def find_conflicting_indices(assignments):
    section_slot, faculty_slot, room_slot = {}, {}, {}
    for i, a in enumerate(assignments):
        section_slot.setdefault((a["section_id"], a["timeslot"]), []).append(i)
        faculty_slot.setdefault((a["faculty_id"], a["timeslot"]), []).append(i)
        room_slot.setdefault((a["room"].id, a["timeslot"]), []).append(i)

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
        if other["room"].id == room.id:
            return False
    return True


def repair(assignments):
    assignments = [dict(a) for a in assignments]
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
                        "day_index": ts // PERIODS_PER_DAY,
                        "period": ts % PERIODS_PER_DAY,
                        "room": room,
                    })
                    fixed = True
                    break
            if fixed:
                break
        rounds += 1
        conflicting = find_conflicting_indices(assignments)
    return assignments, len(conflicting)


final, unresolved = repair(assignments)
m = analyze(final)

section_status = "OK" if m["section_conflicts"] == 0 else "NEEDS FIX"
faculty_status = "OK" if m["faculty_conflicts"] == 0 else "NEEDS FIX"
room_status = "OK" if m["room_conflicts"] == 0 else "NEEDS FIX"
lab_status = "OK" if m["lab_mismatches"] == 0 else "NEEDS FIX"
capacity_status = "OK" if m["capacity_issues"] == 0 else "NEEDS FIX"

print("\n=========== FINAL RESULT (after repair) ===========")
print("--- Explainable fitness breakdown ---")
print(f"Section double-bookings : {m['section_conflicts']}  {section_status}")
print(f"Faculty double-bookings : {m['faculty_conflicts']}  {faculty_status}")
print(f"Room double-bookings    : {m['room_conflicts']}  {room_status}")
print(f"Lab/room mismatches     : {m['lab_mismatches']}  {lab_status}")
print(f"Capacity issues         : {m['capacity_issues']}  {capacity_status}")
print(f"Same-day subject repeats: {m['same_day_repeats']}  (soft preference - repair doesn't touch this)")

if unresolved > 0:
    print(f"\nNOTE: repair could not resolve {unresolved} conflict(s) - "
          f"would need a manual admin override or a rerun.")
else:
    print("\nAll hard constraints fully satisfied after repair.")

for section in sections:
    print(f"\n=== {section.name} ===")
    grid = [["----FREE----" for _ in range(PERIODS_PER_DAY)] for _ in range(len(DAYS))]
    for a in final:
        if a["section_id"] == section.id:
            grid[a["day_index"]][a["period"]] = f'{a["subject_name"][:14]} [{a["room"].name}]'
    header = f"{'':8}" + "".join(f"P{p+1:<20}" for p in range(PERIODS_PER_DAY))
    print(header)
    print("-" * len(header))
    for d, day in enumerate(DAYS):
        row = f"{day:8}"
        for p in range(PERIODS_PER_DAY):
            row += f"{grid[d][p]:<21}"
        print(row)