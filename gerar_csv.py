import os
import cv2
import csv
from ultralytics import YOLO

from config import YOLO_POSE_MODEL_PATH

# Carrega o modelo YOLO Pose uma única vez (evitando recarregamentos repetidos)
pose_model = YOLO(YOLO_POSE_MODEL_PATH)  # Certifique-se de ter esse modelo ou ajuste o caminho


def read_annotations(txt_path):
    """
    Lê o arquivo de anotações e retorna um dicionário no formato:
    {
      "Fighting003_x264.mp4": {
         "event": "Fighting",
         "intervals": [(1820, 3103)],
      },
      "Normal_Videos_015_x264.mp4": {
         "event": "Normal",
         "intervals": [],
      },
      ...
    }
    """
    annotations = {}
    with open(txt_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            video_name = parts[0]
            event_name = parts[1]  # "Fighting" ou "Normal"

            # Converte as próximas 4 colunas em inteiros
            start1, end1 = int(parts[2]), int(parts[3])
            start2, end2 = int(parts[4]), int(parts[5])

            intervals = []
            if start1 != -1 and end1 != -1:
                intervals.append((start1, end1))
            if start2 != -1 and end2 != -1:
                intervals.append((start2, end2))

            annotations[video_name] = {
                "event": event_name,
                "intervals": intervals
            }
    return annotations


def is_frame_in_annotation(frame_number, intervals):
    """
    Retorna 1 se o 'frame_number' estiver em algum intervalo anotado;
    caso contrário, retorna 0.
    """
    for (start, end) in intervals:
        if start <= frame_number <= end:
            return 1
    return 0


def detect_keypoints(frame):
    """
    Utiliza o YOLO Pose para detectar keypoints.
    Retorna uma lista de detecções, onde cada detecção é uma lista com 34 valores:
    [x1, y1, x2, y2, ..., x17, y17].
    Se nenhuma pessoa for detectada, retorna uma lista contendo uma única detecção com 34 zeros.
    """
    # Converte o frame de BGR para RGB
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # Executa a inferência com o modelo YOLO Pose
    results = pose_model(frame_rgb, verbose=False)

    all_detections = []
    if results and len(results) > 0:
        detected = results[0]
        if detected.keypoints is not None and len(detected.keypoints) > 0:
            # Itera sobre todas as pessoas detectadas
            for person in detected.keypoints:
                # Converte o tensor de keypoints para um array NumPy
                kp_array = person.xy.cpu().numpy()

                # Caso o array possua uma dimensão extra (ex.: (1, 17, 2)), removemos a primeira dimensão
                if kp_array.shape[0] == 1:
                    kp_array = kp_array[0]

                coords = []
                # Agora, assumindo que kp_array tem a forma (17, 2)
                for point in kp_array:
                    coords.extend([float(point[0]), float(point[1])])
                # Se não houver 17 pontos, completa com zeros
                if len(coords) < 34:
                    coords.extend([0] * (34 - len(coords)))
                all_detections.append(coords)

    # Se nenhuma pessoa for detectada, retorna uma única "detecção" com zeros
    if not all_detections:
        return [[0] * 34]

    return all_detections


def process_video(video_path, event_name, intervals, output_csv_path):
    """
    Abre o vídeo, lê cada frame, detecta keypoints de todas as pessoas e salva no CSV:
    frame, person_id, x1, y1, x2, y2, ..., x17, y17, label
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[ERROR] Não foi possível abrir o vídeo: {video_path}")
        return
    frame_count = 0

    with open(output_csv_path, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)

        # Monta o cabeçalho do CSV
        header = ["frame", "person_id"]
        for i in range(1, 18):
            header.append(f"x{i}")
            header.append(f"y{i}")
        header.append("label")
        writer.writerow(header)

        # Processa cada frame
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frame_count += 1

            # Detecta keypoints usando YOLO Pose para todas as pessoas
            detections = detect_keypoints(frame)

            # Define o label: se for "Fighting" e o frame estiver no intervalo anotado, label = 1; caso contrário, 0.
            if event_name == "Fighting":
                label = is_frame_in_annotation(frame_count, intervals)
            else:
                label = 0

            # Salva uma linha para cada pessoa detectada
            for person_id, keypoints in enumerate(detections):
                row = [frame_count, person_id] + keypoints + [label]
                writer.writerow(row)

    cap.release()
    print(f"[INFO] Processado: {video_path} -> {output_csv_path} (Frames: {frame_count})")


def main():
    # Ajuste os caminhos conforme sua estrutura de diretórios
    annotations_file = os.path.join("annotations", "temporal_annotation.txt")
    dataset_dir = os.path.join("dataset")
    csv_output_dir = os.path.join("csv")

    os.makedirs(csv_output_dir, exist_ok=True)

    # Lê as anotações
    annotations = read_annotations(annotations_file)

    # Para cada vídeo anotado, processa e gera o CSV correspondente
    for video_name, info in annotations.items():
        event_name = info["event"]  # "Fighting" ou "Normal"
        intervals = info["intervals"]  # [(start1, end1), (start2, end2)]

        video_path = os.path.join(dataset_dir, video_name)
        output_csv_path = os.path.join(csv_output_dir, f"{os.path.splitext(video_name)[0]}.csv")

        print(f"[INFO] Iniciando processamento de {video_name} (evento: {event_name})")
        process_video(video_path, event_name, intervals, output_csv_path)


if __name__ == "__main__":
    main()
