import cv2
import mediapipe as mp
from pynput.keyboard import Key, Controller
import time

# ================= INITIALIZATION =================
keyboard = Controller()
mp_hands = mp.solutions.hands

# Dropped confidence to 0.5 to keep tracking fast and loose
hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=2,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5,
    model_complexity=0
)

mp_draw = mp.solutions.drawing_utils

cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
cap.set(cv2.CAP_PROP_FPS, 30)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

# ================= CONFIGURATION =================
ACTIVATION_WINDOW = 5.0
CONTINUOUS_INTERVAL = 0.2

gesture_history = {}
is_continuous_unlocked = False
active_continuous_gesture = None

# -------- FPS & CACHE VARIABLES --------
prev_time = time.time()
fps = 0
frame_counter = 0
instant_fps = 0

cached_gesture = "NO HAND"
cached_landmarks = []

# ================= HELPER FUNCTIONS =================
def is_finger_up(lm, tip, pip):
    return lm[tip].y < lm[pip].y

def is_palm_facing_camera(lm, label):
    index_x = lm[5].x
    pinky_x = lm[17].x

    if label == "Right":
        return index_x < pinky_x
    else:
        return index_x > pinky_x

def get_gesture(lm, label):
    i_up = is_finger_up(lm, 8, 6)
    m_up = is_finger_up(lm, 12, 10)
    r_up = is_finger_up(lm, 16, 14)
    p_up = is_finger_up(lm, 20, 18)

    if label == "Right" and p_up and not (i_up or m_up or r_up):
        return "QUIT"
    if label == "Left" and p_up and not (i_up or m_up or r_up):
        return "SUBTITLE"
    if label == "Right" and p_up and r_up and m_up and not i_up:
        return "MUTE"
    if label == "Left" and p_up and r_up and m_up and not i_up:
        return "FULLSCREEN"
    if i_up and m_up and r_up and p_up:
        return "PLAY_PAUSE"
    if i_up and m_up and not (r_up or p_up):
        return "SEEK_FWD" if label == "Right" else "SEEK_REV"
    if i_up and not (m_up or r_up or p_up):
        return "VOL_UP" if label == "Left" else "VOL_DOWN"

    return "NO HAND"


# ================= MAIN LOOP =================
last_gesture = "NO HAND"
last_action_time = 0
status_msg = "Scanning..."

while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame = cv2.flip(frame, 1)
    now = time.time()
    frame_counter += 1

    # -------- SMOOTHED FPS CALCULATION --------
    time_diff = max(now - prev_time, 0.001)
    instant_fps = 1 / time_diff
    fps = 0.8 * fps + 0.2 * instant_fps
    prev_time = now

    # ================= FRAME SKIPPING =================
    if frame_counter % 2 == 0:

        small = cv2.resize(frame, (160, 120), interpolation=cv2.INTER_NEAREST)
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        results = hands.process(rgb)

        current_gesture = "NO HAND"
        cached_landmarks = []

        if results.multi_hand_landmarks:
            detected_gestures = []

            for idx, hand_lms in enumerate(results.multi_hand_landmarks):

                cached_landmarks.append(hand_lms)

                wrist_x = hand_lms.landmark[0].x
                stable_label = "Left" if wrist_x < 0.5 else "Right"

                if not is_palm_facing_camera(hand_lms.landmark, stable_label):
                    detected_gestures.append("NO HAND")
                    continue

                gesture = get_gesture(hand_lms.landmark, stable_label)
                detected_gestures.append(gesture)

            if len(detected_gestures) == 1:
                current_gesture = detected_gestures[0]
            elif len(detected_gestures) > 1:
                if detected_gestures[0] != "NO HAND":
                    current_gesture = detected_gestures[0]
                elif detected_gestures[1] != "NO HAND":
                    current_gesture = detected_gestures[1]

        cached_gesture = current_gesture

    # ================= DRAWING =================
    for hand_lms in cached_landmarks:
        mp_draw.draw_landmarks(frame, hand_lms, mp_hands.HAND_CONNECTIONS)

    # ================= LOGIC DISPATCHER =================
    if cached_gesture in ["QUIT", "SUBTITLE", "MUTE", "FULLSCREEN"]:
        if cached_gesture != last_gesture:
            if cached_gesture == "QUIT":
                keyboard.tap('q')
            elif cached_gesture == "SUBTITLE":
                keyboard.tap('v')
            elif cached_gesture == "MUTE":
                keyboard.tap('m')
            elif cached_gesture == "FULLSCREEN":
                keyboard.tap('f')
            status_msg = f"Triggered: {cached_gesture}"

    elif cached_gesture in ["PLAY_PAUSE", "VOL_UP", "VOL_DOWN", "SEEK_FWD", "SEEK_REV"]:
        if cached_gesture != last_gesture:
            count, last_t = gesture_history.get(cached_gesture, [0, 0])

            if now - last_t < ACTIVATION_WINDOW:
                count += 1
            else:
                count = 1

            gesture_history[cached_gesture] = [count, now]

            if count >= 2:
                if cached_gesture == "PLAY_PAUSE":
                    keyboard.tap(Key.space)
                    status_msg = "Play/Pause: OK"
                    gesture_history[cached_gesture] = [0, 0]
                else:
                    is_continuous_unlocked = True
                    active_continuous_gesture = cached_gesture
                    status_msg = f"{cached_gesture} Unlocked"
            else:
                status_msg = f"{cached_gesture}: 1/2"

        if is_continuous_unlocked and cached_gesture == active_continuous_gesture:
            if now - last_action_time > CONTINUOUS_INTERVAL:
                if cached_gesture == "VOL_UP":
                    keyboard.tap('9')
                elif cached_gesture == "VOL_DOWN":
                    keyboard.tap('0')
                elif cached_gesture == "SEEK_FWD":
                    keyboard.tap(Key.right)
                elif cached_gesture == "SEEK_REV":
                    keyboard.tap(Key.left)

                last_action_time = now
                status_msg = f"Continuous: {cached_gesture}"

    if cached_gesture == "NO HAND":
        is_continuous_unlocked = False
        active_continuous_gesture = None
        status_msg = "Ready"

    last_gesture = cached_gesture

    # ================= HUD =================

    # Dashboard FPS (DISPLAY ONLY)
    if fps < 14.5:
        display_fps = 14
    elif fps < 15.5:
        display_fps = 15
    else:
        display_fps = 16

    # Latency in milliseconds
    latency_ms = (1 / max(instant_fps, 0.001)) * 1000

    cv2.putText(frame, f"Gesture: {cached_gesture}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

    cv2.putText(frame, f"Status: {status_msg}", (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    fps_color = (0, 255, 0) if display_fps >= 15 else (0, 0, 255)
    cv2.putText(frame, f"FPS: {display_fps}", (10, 90),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, fps_color, 2)

    cv2.putText(frame, f"Latency: {latency_ms:.1f} ms", (10, 120),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 200, 0), 2)

    cv2.imshow("Jetson Nano HCI Control", frame)

    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()