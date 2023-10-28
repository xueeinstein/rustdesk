import re
import cv2
import argparse


def draw_arrow(frame,
               pos,
               direction,
               arrow_color=(0, 0, 255),
               thickness=2,
               arrow_length=20):
    if direction == 'up':
        tip = (pos[0], pos[1] - arrow_length)
        cv2.line(frame, pos, tip, arrow_color, thickness)
        cv2.line(frame, tip, (tip[0] - 5, tip[1] + 10), arrow_color, thickness)
        cv2.line(frame, tip, (tip[0] + 5, tip[1] + 10), arrow_color, thickness)
    elif direction == 'down':
        tip = (pos[0], pos[1] + arrow_length)
        cv2.line(frame, pos, tip, arrow_color, thickness)
        cv2.line(frame, tip, (tip[0] - 5, tip[1] - 10), arrow_color, thickness)
        cv2.line(frame, tip, (tip[0] + 5, tip[1] - 10), arrow_color, thickness)
    elif direction == 'left':
        tip = (pos[0] - arrow_length, pos[1])
        cv2.line(frame, pos, tip, arrow_color, thickness)
        cv2.line(frame, tip, (tip[0] + 10, tip[1] - 5), arrow_color, thickness)
        cv2.line(frame, tip, (tip[0] + 10, tip[1] + 5), arrow_color, thickness)
    elif direction == 'right':
        tip = (pos[0] + arrow_length, pos[1])
        cv2.line(frame, pos, tip, arrow_color, thickness)
        cv2.line(frame, tip, (tip[0] - 10, tip[1] - 5), arrow_color, thickness)
        cv2.line(frame, tip, (tip[0] - 10, tip[1] + 5), arrow_color, thickness)


def visualize_demo(input_webm, action_log, output_mp4):
    cap = cv2.VideoCapture(input_webm)
    if not cap.isOpened():
        print("Error: Could not open the WebM file.")
        exit()

    # fps = cap.get(cv2.CAP_PROP_FPS)
    fps = 30
    num_frame = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    alog = open(action_log, 'r')
    pattern = r'event_type:\s+(\w+(?:\(.+?\))?)(?=\s+})'

    def _read_alog():
        has_act, data = True, None
        try:
            # ms:6073,event_type:KeyPress(MetaLeft)
            line = alog.readline().strip()

            ms = int(line.split(',')[0].split(':')[1])

            if 'MouseMove' in line:
                # ms:1720,event_type:MouseMove { x: 1269.0, y: 832.0 }
                args = re.search(r'x: (\d+\.\d+), y: (\d+\.\d+)', line)
                x = float(args.group(1))
                y = float(args.group(2))
                data = {'ms': ms, 'event_type': 'mouse_move', 'x': x, 'y': y}

            elif 'Wheel' in line:
                # ms:4056,event_type:Wheel { delta_x: 0, delta_y: -1 }
                args = re.search(r'delta_x:\s*(-?\d+),\s*delta_y:\s*(-?\d+)',
                                 line)
                dx = float(args.group(1))
                dy = float(args.group(2))
                data = {'ms': ms, 'event_type': 'wheel', 'dx': dx, 'dy': dy}

            elif 'KeyPress' in line:
                # ms:7296,event_type:KeyPress(F1)
                args = re.search(r'event_type:KeyPress\((.*?)\)', line)
                key = args.group(1)
                data = {'ms': ms, 'event_type': 'key_press', 'key': key}

            elif 'KeyRelease' in line:
                args = re.search(r'event_type:KeyRelease\((.*?)\)', line)
                key = args.group(1)
                data = {'ms': ms, 'event_type': 'key_release', 'key': key}

            elif 'ButtonPress' in line:
                args = re.search(r'event_type:ButtonPress\((.*?)\)', line)
                btn = args.group(1)
                data = {'ms': ms, 'event_type': 'button_press', 'button': btn}

            elif 'ButtonRelease' in line:
                args = re.search(r'event_type:ButtonRelease\((.*?)\)', line)
                btn = args.group(1)
                data = {
                    'ms': ms,
                    'event_type': 'button_release',
                    'button': btn
                }

        except Exception:
            has_act = False

        return has_act, data

    out_cap = None
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out_cap = cv2.VideoWriter(output_mp4, fourcc, fps, (w, h))

    blue = (255, 0, 0)
    green = (255, 0, 0)
    red = (0, 0, 255)
    orange = (0, 165, 255)

    states = {
        'key': None,
        'btn': None,
        'wheel': None,
        'mx': w // 2,
        'my': h // 2
    }

    def _parse_event(act):
        if act['event_type'] != 'wheel':
            states['wheel'] = None

        if act['event_type'] == 'mouse_move':
            states['mx'] = int(act['x'])
            states['my'] = int(act['y'])

        elif act['event_type'] == 'button_press':
            states['btn'] = act['button']

        elif act['event_type'] == 'button_release':
            states['btn'] = None

        elif act['event_type'] == 'key_press':
            if states['key'] is not None:
                states['key'].append(act['key'])
            else:
                states['key'] = [act['key']]

        elif act['event_type'] == 'key_release':
            i = states['key'].index(act['key'])
            states['key'].pop(i)
            if len(states['key']) == 0:
                states['key'] = None

        elif act['event_type'] == 'wheel':
            states['wheel'] = (act['dx'], act['dy'])

    ms = 0
    has_act = True
    while has_act:
        has_act, act = _read_alog()
        print(act)

        if has_act:
            _parse_event(act)
        else:
            break

        if ms > act['ms']:
            # Act log is faster
            continue

        # Act log is slower
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            ms = int(cap.get(cv2.CAP_PROP_POS_MSEC))
            print(ms)

            # Mouse
            if states['btn'] is None and states['wheel'] is None:
                mx, my = states['mx'], states['my']
                cv2.circle(frame, (mx, my), 5, red, 2)

            elif states['btn'] is None and states['wheel'] is not None:
                wheel = states['wheel']
                if wheel[0] == 0 and wheel[1] == 1:
                    draw_arrow(frame, (mx, my), 'up')
                elif wheel[0] == 0 and wheel[1] == -1:
                    draw_arrow(frame, (mx, my), 'down')

            elif states['btn'] is not None:
                if states['btn'].lower() == 'left':
                    cv2.circle(frame, (mx, my), 5, orange, -1)
                elif states['btn'].lower() == 'right':
                    cv2.circle(frame, (mx, my), 5, green, -1)

            # Keyboard
            if states['key'] is not None:
                s = ' + '.join(states['key'])
                font = cv2.FONT_HERSHEY_SIMPLEX
                font_scale = 1
                font_thickness = 2
                text_size = cv2.getTextSize(s, font, font_scale,
                                            font_thickness)[0]
                cv2.putText(frame, s, (w // 2 - text_size[0] // 2, h - 50),
                            font, font_scale, red, font_thickness)

            out_cap.write(frame)
            if ms < act['ms']:
                continue
            else:
                break

    cap.release()
    out_cap.release()
    alog.close()


if __name__ == '__main__':
    import sys
    parser = argparse.ArgumentParser()
    parser.add_argument('-w',
                        '--webm_file',
                        type=str,
                        help='Path to input webm file')
    parser.add_argument('-a', '--act_log', type=str, help='Path to action log')
    parser.add_argument('-o',
                        '--output_vis',
                        type=str,
                        help='Path to visualization video')
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)

    args = parser.parse_args()

    visualize_demo(args.webm_file, args.act_log, args.output_vis)
