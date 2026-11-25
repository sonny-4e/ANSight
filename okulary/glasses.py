import sys
import pandas as pd

def load_file(path):
    if path.endswith(".xlsx"):
        return pd.read_excel(path)
    elif path.endswith(".tsv"):
        return pd.read_csv(path, sep="\t", encoding="utf-8-sig", decimal=",")
    elif path.endswith(".csv"):
        return pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig", decimal=",")
    else:
        return None

def extract_eye_tracker_sensors_data(df):
    columns = ["Sensor", "Recording timestamp", "Pupil diameter left", "Pupil diameter right",
               "Gaze point X", "Gaze point Y", "Validity left", "Validity right"]

    missing_columns = []

    for column in columns:
        if column not in df.columns:
            missing_columns.append(column)

    if missing_columns:
        print(f"Blad: Brakujace kolumny: {missing_columns}")
        return None

    eye_tracker_sensors = df[df["Sensor"] == "Eye Tracker"].copy()
    # Usuwamy kolumne Sensor, sprawdzalismy ja wczesniej tylko po to by bledu gdzies dalej nie rzucilo, ale jej nie analizujemy
    eye_tracker_sensors = eye_tracker_sensors[columns[1:]]

    return eye_tracker_sensors

def get_recording_summary(df):
    participant_name = df["Participant name"].dropna().iloc[0]
    recording_name = df["Recording name"].dropna().iloc[0]
    recording_start_time = df["Recording start time"].dropna().iloc[0]
    recording_duration = df["Recording duration"].dropna().iloc[0]

    return {
        "Uczestnik": participant_name,
        "Nazwa nagrania": recording_name,
        "Godzina rozpoczęcia nagrania": recording_start_time,
        "Czas trwania nagrania (ms)": recording_duration
    }

def get_time_summary(df):
    # errors="coerce" zmienia tekst w NaN, a dropna() usuwa wszystkie NaN'y
    recording_timestamps = pd.to_numeric(df["Recording timestamp"], errors="coerce").dropna()

    # Potrzebujemy minimum dwoch znacznikow czasu, zeby obliczyc odstep miedzy nimi
    if len(recording_timestamps) < 2:
        print("Blad: Zbyt malo danych do obliczenia czestotliwosci")
        return None

    # Obliczamy roznice miedzy elementem n+1 a n, usuwamy NaN'y i niedodatnie wartosci
    differences = recording_timestamps.diff().dropna()
    differences = differences[differences > 0]

    if differences.empty:
        print("Blad: Nie mozna obliczyc odstepu miedzy probkami")
        return None

    # Liczymy mediane, bo pojedyncza przerwa nam jej nie popsuje, a srednia moze popsuc
    median_interval = differences.median()

    return {
        "Pierwsza probka (ms)": recording_timestamps.iloc[0],
        "Ostatnia probka (ms)": recording_timestamps.iloc[-1],
        "Mediana odstepu (ms)": median_interval,
        "Czestotliwosc probkowania (Hz)": 1000 / median_interval
    }

def get_eye_data_summary(df):
    total = len(df)

    left_pupil_diameter = df["Pupil diameter left"]
    right_pupil_diameter = df["Pupil diameter right"]

    left_mean = left_pupil_diameter.mean()
    right_mean = right_pupil_diameter.mean()

    left_missing = left_pupil_diameter.isna().sum()
    right_missing = right_pupil_diameter.isna().sum()

    left_missing_percentage = left_missing / total * 100
    right_missing_percentage = right_missing / total * 100

    left_valid = (df["Validity left"] == "Valid").sum()
    left_invalid = (df["Validity left"] == "Invalid").sum()

    right_valid = (df["Validity right"] == "Valid").sum()
    right_invalid = (df["Validity right"] == "Invalid").sum()

    left_valid_percentage = left_valid / total * 100
    right_valid_percentage = right_valid / total * 100

    gaze_missing = df[["Gaze point X", "Gaze point Y"]].isna().any(axis=1).sum()
    gaze_missing_percentage = gaze_missing / total * 100

    gaze_complete = total - gaze_missing
    gaze_complete_percentage = gaze_complete / total * 100

    return {
        "Srednia srednica lewej zrenicy (mm)": left_mean,
        "Srednia srednica prawej zrenicy (mm)": right_mean,
        "Brakujace pomiary lewego oka": left_missing,
        "Brakujace pomiary prawego oka": right_missing,
        "Brakujace pomiary lewego oka (%)": left_missing_percentage,
        "Brakujace pomiary prawego oka (%)": right_missing_percentage,
        "Prawidlowe pomiary lewego oka": left_valid,
        "Nieprawidlowe pomiary lewego oka": left_invalid,
        "Prawidlowe pomiary prawego oka": right_valid,
        "Nieprawidlowe pomiary prawego oka": right_invalid,
        "Poprawne pomiary lewego oka (%)": left_valid_percentage,
        "Poprawne pomiary prawego oka (%)": right_valid_percentage,
        "Brakujace punkty spojrzenia": gaze_missing,
        "Brakujace punkty spojrzenia (%)": gaze_missing_percentage,
        "Kompletne punkty spojrzenia": gaze_complete,
        "Kompletne punkty spojrzenia (%)": gaze_complete_percentage
    }

def save_results(eye_data, summary, path):
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        summary_df = pd.DataFrame(list(summary.items()), columns=["Parametr", "Wartosc"])

        summary_df.to_excel(writer, sheet_name="Podsumowanie", index=False)

        worksheet = writer.sheets["Podsumowanie"]

        worksheet.column_dimensions["A"].width = 40
        worksheet.column_dimensions["B"].width = 20

        worksheet.freeze_panes = "A2"

        eye_data.to_excel(writer, sheet_name="Dane oczu", index=False)

        worksheet = writer.sheets["Dane oczu"]

        worksheet.auto_filter.ref = worksheet.dimensions

        for column in worksheet.columns:
            max_length = max(len(str(cell.value or "")) for cell in column)
            worksheet.column_dimensions[column[0].column_letter].width = max_length

        worksheet.freeze_panes = "A2"

    print(f"Wyniki zostaly zapisane w pliku: {path}")

def main():
    if len(sys.argv) < 2:
        print("Uzycie: python glasses.py sciezka/do/pliku/z/rozszerzeniem")
        return 1

    df = load_file(sys.argv[1])

    if df is None:
        print("Blad: Nieprawidlowe rozszerzenie pliku")
        return 1

    if df.empty:
        print("Blad: Plik nie zawiera danych")
        return 1

    eye_data = extract_eye_tracker_sensors_data(df)

    if eye_data is None:
        return 1

    summary = get_recording_summary(df)

    time_summary = get_time_summary(eye_data)

    if time_summary is None:
        return 1

    summary.update(time_summary)
    summary.update(get_eye_data_summary(eye_data))

    path = sys.argv[1].rsplit(".", 1)[0] + "_analysis.xlsx"
    save_results(eye_data, summary, path)

    return 0

if __name__ == "__main__":
    sys.exit(main())