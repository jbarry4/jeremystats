# A dictionary of 3 patients, each keyed by their patient ID
patients = {
    "P001": {
        "name": "Alice Nguyen",
        "age": 34,
        "arrival_date": "2026-06-21",
        "diagnosis": "Asthma",
        "room": "A12",
    },
    "P002": {
        "name": "Marcus Lee",
        "age": 58,
        "arrival_date": "2026-06-23",
        "diagnosis": "Hypertension",
        "room": "B07",
    },
    "P003": {
        "name": "Sofia Reyes",
        "age": 27,
        "arrival_date": "2026-06-25",
        "diagnosis": "Fractured wrist",
        "room": "C03",
    },
}

# Loop through each patient and print their ID and arrival date
for patient_id, info in patients.items():
    print(f"ID: {patient_id}  |  Arrival date: {info['arrival_date']}")
