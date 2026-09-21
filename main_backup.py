############################################# IMPORTING ################################################
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox as mess
from tkinter import PhotoImage
from PIL import Image, ImageTk
import tkinter.simpledialog as tsd
import cv2
import os
import csv
import numpy as np
from PIL import Image
import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.utils import get_column_letter
import datetime
import time
import shutil
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import sys
import platform  # For Caps Lock detection
from subprocess import check_output, CalledProcessError

# Ensure working directory is set to the script folder
os.chdir(os.path.dirname(os.path.abspath(__file__)))

############################################# FUNCTIONS ################################################

def assure_path_exists(path):
    os.makedirs(path, exist_ok=True)

##################################################################################

def tick():
    # Get the current time
    current_time = time.strftime('%I:%M:%S %p')
    # Update the clock label with the current time
    clock.config(text=current_time)
    # Schedule the next update after 1000 milliseconds (1 second)
    clock.after(1000, tick)

###################################################################################

def contact():
    mess._show(title='Contact us', message="Please contact us on : 'dasdarshan7@gmail.com' ")

###################################################################################

def check_haarcascadefile():
    exists = os.path.isfile("haarcascade_frontalface_default.xml")
    if exists:
        return True
    else:
        mess._show(title='Some file missing', message='Please make sure "haarcascade_frontalface_default.xml" exists in the application folder.')
        return False

######################################## CAPS LOCK DETECTION ########################################

def is_capslock_on():
    """
    Cross-platform Caps Lock state checker.
    Works on Windows, macOS, and common Linux setups.
    Returns True if Caps Lock is ON, False otherwise.
    """
    system = platform.system()
    try:
        # --- Windows ---
        if system == "Windows":
            import ctypes
            hll = ctypes.WinDLL("User32.dll")
            VK_CAPITAL = 0x14
            state = hll.GetKeyState(VK_CAPITAL)
            return bool(state & 0x0001)  # low-order bit indicates toggle
        # --- macOS ---
        elif system == "Darwin":
            try:
                from Quartz import CGEventSourceKeyState, kCGEventSourceStateHIDSystemState
                # 57 is the Caps Lock virtual key on macOS
                return bool(CGEventSourceKeyState(kCGEventSourceStateHIDSystemState, 57))
            except Exception:
                # pyobjc may not be installed — can't detect
                return False
        # --- Linux ---
        elif system == "Linux":
            # Try xset (X11)
            try:
                out = check_output(["xset", "q"]).decode(errors='ignore')
                return "Caps Lock:   on" in out or "Caps Lock: on" in out
            except (CalledProcessError, FileNotFoundError):
                # xset not available (Wayland or headless) — no reliable detection
                return False
        else:
            return False
    except Exception:
        return False

# Continuous Caps Lock warning for any Entry field
def check_capslock_continuous(entry_widget, warning_label):
    try:
        if is_capslock_on():
            warning_label.config(text="⚠ Caps Lock is ON!")
        else:
            warning_label.config(text="")
    except Exception:
        warning_label.config(text="")
    entry_widget.after(200, lambda: check_capslock_continuous(entry_widget, warning_label))

###################################################################################

def autofit_excel(file_path):
    """
    Auto-fit column widths for all sheets in the given workbook file_path (openpyxl).
    """
    try:
        wb = load_workbook(file_path)
    except Exception:
        return
    for ws in wb.worksheets:
        for col in ws.columns:
            max_length = 0
            try:
                col_letter = get_column_letter(col[0].column)
            except Exception:
                continue
            for cell in col:
                try:
                    if cell.value is not None:
                        length = len(str(cell.value))
                        if length > max_length:
                            max_length = length
                except Exception:
                    pass
            adjusted_width = (max_length + 2)
            if adjusted_width < 8:
                adjusted_width = 8
            ws.column_dimensions[col_letter].width = adjusted_width
    try:
        wb.save(file_path)
    except Exception:
        pass

###################################################################################

def save_pass():
    assure_path_exists("TrainingImageLabel/")
    exists1 = os.path.isfile(os.path.join("TrainingImageLabel", "psd.txt"))
    if exists1:
        tf = open(os.path.join("TrainingImageLabel", "psd.txt"), "r")
        key = tf.read()
        tf.close()
    else:
        master.destroy()
        new_pas = tsd.askstring('Old Password not found', 'Please enter a new password below', show='*')
        if new_pas is None:
            mess._show(title='No Password Entered', message='Password not set!! Please try again')
            return
        else:
            with open(os.path.join("TrainingImageLabel", "psd.txt"), "w") as tf:
                tf.write(new_pas)
            mess._show(title='Password Registered', message='New password was registered successfully!!')
            return
    op = (old.get())
    newp = (new.get())
    nnewp = (nnew.get())
    if (op == key):
        if (newp == nnewp):
            with open(os.path.join("TrainingImageLabel", "psd.txt"), "w") as txf:
                txf.write(newp)
        else:
            mess._show(title='Error', message='Confirm new password again!!!')
            return
    else:
        mess._show(title='Wrong Password', message='Please enter correct old password.')
        return
    mess._show(title='Password Changed', message='Password changed successfully!!')
    master.destroy()

###################################################################################

def change_pass():
    global master
    master = tk.Tk()
    master.geometry("420x200")
    master.resizable(False, False)
    master.title("Change Password")
    master.configure(background="white")
    lbl4 = tk.Label(master, text='Enter Old Password', bg='white', font=('comic', 12, ' bold '))
    lbl4.place(x=10, y=10)
    global old
    old = tk.Entry(master, width=22, fg="black", relief='solid', font=('comic', 12, ' bold '), show='*')
    old.place(x=200, y=10)
    old_warning = tk.Label(master, text="", bg='white', fg='red', font=('comic', 10, ' bold '))
    old_warning.place(x=200, y=35)
    old.bind("<KeyPress>", lambda e: check_capslock_continuous(old, old_warning))

    # Toggle for old
    def toggle_old():
        if old.cget('show') == '':
            old.config(show='*')
            btn_old.config(text='Show')
        else:
            old.config(show='')
            btn_old.config(text='Hide')

    btn_old = tk.Button(master, text='Show', command=toggle_old, width=6)
    btn_old.place(x=340, y=8)

    lbl5 = tk.Label(master, text='Enter New Password', bg='white', font=('comic', 12, ' bold '))
    lbl5.place(x=10, y=60)
    global new
    new = tk.Entry(master, width=22, fg="black", relief='solid', font=('comic', 12, ' bold '), show='*')
    new.place(x=200, y=60)
    new_warning = tk.Label(master, text="", bg='white', fg='red', font=('comic', 10, ' bold '))
    new_warning.place(x=200, y=85)
    new.bind("<KeyPress>", lambda e: check_capslock_continuous(new, new_warning))

    # Toggle for new
    def toggle_new():
        if new.cget('show') == '':
            new.config(show='*')
            btn_new.config(text='Show')
        else:
            new.config(show='')
            btn_new.config(text='Hide')

    btn_new = tk.Button(master, text='Show', command=toggle_new, width=6)
    btn_new.place(x=340, y=58)

    lbl6 = tk.Label(master, text='Confirm New Password', bg='white', font=('comic', 12, ' bold '))
    lbl6.place(x=10, y=110)
    global nnew
    nnew = tk.Entry(master, width=22, fg="black", relief='solid', font=('comic', 12, ' bold '), show='*')
    nnew.place(x=200, y=110)
    nnew_warning = tk.Label(master, text="", bg='white', fg='red', font=('comic', 10, ' bold '))
    nnew_warning.place(x=200, y=135)
    nnew.bind("<KeyPress>", lambda e: check_capslock_continuous(nnew, nnew_warning))

    # Toggle for confirm new
    def toggle_nnew():
        if nnew.cget('show') == '':
            nnew.config(show='*')
            btn_nnew.config(text='Show')
        else:
            nnew.config(show='')
            btn_nnew.config(text='Hide')

    btn_nnew = tk.Button(master, text='Show', command=toggle_nnew, width=6)
    btn_nnew.place(x=340, y=108)

    cancel = tk.Button(master, text="Cancel", command=master.destroy, fg="black", bg="red",
                       height=1, width=25, activebackground="white", font=('comic', 10, ' bold '))
    cancel.place(x=200, y=150)

    save1 = tk.Button(master, text="Save", command=save_pass, fg="black", bg="#00fcca",
                      height=1, width=25, activebackground="white", font=('comic', 10, ' bold '))
    save1.place(x=10, y=150)
    master.mainloop()

#####################################################################################

# -- New helper: custom password dialog with visibility toggle and caps-lock warning --
def ask_password_dialog(title="Password", prompt="Enter Password", require_confirm=False):
    """
    Opens a modal Toplevel dialog that asks for a password.
    If require_confirm is True, asks for password + confirm password and returns the password only if they match.
    Returns the entered password (string) or None if cancelled.
    """
    result = {"password": None}
    dialog = tk.Toplevel()
    dialog.transient(window if 'window' in globals() else None)
    dialog.grab_set()
    dialog.title(title)
    dialog.geometry("420x200" if require_confirm else "420x140")
    dialog.resizable(False, False)
    dialog.configure(bg="white")

    lbl = tk.Label(dialog, text=prompt, bg='white', font=('comic', 11, ' bold '))
    lbl.place(x=10, y=10)

    pwd_var = tk.StringVar()
    pwd_entry = tk.Entry(dialog, textvariable=pwd_var, width=30, show='*', font=('comic', 12, ' bold '))
    pwd_entry.place(x=10, y=40)
    pwd_entry.focus_set()

    pwd_warning = tk.Label(dialog, text="", bg='white', fg='red', font=('comic', 9, ' bold '))
    pwd_warning.place(x=10, y=70)
    pwd_entry.bind("<KeyPress>", lambda e: check_capslock_continuous(pwd_entry, pwd_warning))

    # Toggle visibility
    def toggle_pwd():
        if pwd_entry.cget('show') == '':
            pwd_entry.config(show='*')
            toggle_btn.config(text='Show')
        else:
            pwd_entry.config(show='')
            toggle_btn.config(text='Hide')

    toggle_btn = tk.Button(dialog, text='Show', command=toggle_pwd, width=6)
    toggle_btn.place(x=320, y=38)

    confirm_entry = None
    if require_confirm:
        confirm_lbl = tk.Label(dialog, text='Confirm Password', bg='white', font=('comic', 11, ' bold '))
        confirm_lbl.place(x=10, y=95)
        confirm_var = tk.StringVar()
        confirm_entry = tk.Entry(dialog, textvariable=confirm_var, width=30, show='*', font=('comic', 12, ' bold '))
        confirm_entry.place(x=10, y=120)
        confirm_warning = tk.Label(dialog, text="", bg='white', fg='red', font=('comic', 9, ' bold '))
        confirm_warning.place(x=10, y=145)
        confirm_entry.bind("<KeyPress>", lambda e: check_capslock_continuous(confirm_entry, confirm_warning))

        # toggle for confirm
        def toggle_confirm():
            if confirm_entry.cget('show') == '':
                confirm_entry.config(show='*')
                toggle_confirm_btn.config(text='Show')
            else:
                confirm_entry.config(show='')
                toggle_confirm_btn.config(text='Hide')

        toggle_confirm_btn = tk.Button(dialog, text='Show', command=toggle_confirm, width=6)
        toggle_confirm_btn.place(x=320, y=118)

    # OK/Cancel actions
    def on_ok():
        pwd = pwd_var.get()
        if require_confirm:
            conf = confirm_var.get()
            if pwd == "":
                mess._show(title='No Password', message='Please enter a password.')
                return
            if pwd != conf:
                mess._show(title='Mismatch', message='Passwords do not match.')
                return
        result['password'] = pwd
        dialog.destroy()

    def on_cancel():
        dialog.destroy()

    ok_btn = tk.Button(dialog, text="OK", width=10, command=on_ok)
    ok_btn.place(x=240, y=(150 if require_confirm else 100))
    cancel_btn = tk.Button(dialog, text="Cancel", width=10, command=on_cancel)
    cancel_btn.place(x=340, y=(150 if require_confirm else 100))

    dialog.wait_window()
    return result['password']

###################################################################################

def psw():
    """
    Modified psw(): uses a custom dialog with show/hide toggle instead of simpledialog.askstring.
    Behavior:
    - If psd.txt exists: ask for password and if matches, call TrainImages()
    - If psd.txt does NOT exist: ask user to create a new password (with confirmation)
    """
    assure_path_exists("TrainingImageLabel/")
    psd_path = os.path.join("TrainingImageLabel", "psd.txt")
    if os.path.isfile(psd_path):
        # Ask for existing password (single entry with toggle)
        entered = ask_password_dialog(title='Password', prompt='Enter Password', require_confirm=False)
        if entered is None:
            # cancelled
            return
        with open(psd_path, "r") as tf:
            key = tf.read()
        if entered == key:
            TrainImages()
        else:
            mess._show(title='Wrong Password', message='You have entered wrong password')
    else:
        # No password exists -> ask user to create new password (confirm required)
        new_pas = ask_password_dialog(title='Set New Password', prompt='Enter new password', require_confirm=True)
        if new_pas is None:
            mess._show(title='No Password Entered', message='Password not set!! Please try again')
            return
        with open(psd_path, "w") as tf:
            tf.write(new_pas)
        mess._show(title='Password Registered', message='New password was registered successfully!!')
        return

######################################################################################

def clear():
    txt.delete(0, 'end')
    res = "1)Take Images  >>>  2)Save Profile"
    message1.configure(text=res)

def clear2():
    txt2.delete(0, 'end')
    res = "1)Take Images  >>>  2)Save Profile"
    message1.configure(text=res)

#######################################################################################

# File path for StudentDetails
student_details_folder = "StudentDetails"
student_details_file = os.path.join(student_details_folder, "StudentDetails.xlsx")

assure_path_exists(student_details_folder)

def compute_registration_count():
    try:
        df = pd.read_excel(student_details_file)
        df = df.dropna(how='all')
        if 'SERIAL NO.' in df.columns:
            valid = df['SERIAL NO.'].apply(lambda x: str(x).isdigit() if pd.notna(x) else False)
            return int(valid.sum())
        else:
            # fallback
            return max(0, len(df) - 1)
    except Exception:
        return 0

def update_registration_counter():
    """
    Updates the registration counter based on StudentDetails.xlsx accurately.
    Skips headers and empty rows.
    """
    count = 0
    if os.path.exists(student_details_file):
        try:
            df = pd.read_excel(student_details_file)
            df = df.dropna(how='all')
            if 'SERIAL NO.' in df.columns:
                valid = df['SERIAL NO.'].apply(lambda x: str(x).isdigit() if pd.notna(x) else False)
                count = int(valid.sum())
            else:
                count = max(0, len(df) - 1)
        except Exception as e:
            print("Error counting registrations:", e)
            count = 0
    message.configure(text='Total Registrations till now: ' + str(count))

#######################################################################################

def TakeImages():
    if not check_haarcascadefile():
        return
    assure_path_exists("StudentDetails")
    assure_path_exists("TrainingImage")

    # Ensure StudentDetails workbook exists with clean header
    if not os.path.isfile(student_details_file):
        try:
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Students"
            sheet.append(['SERIAL NO.', '', 'ID', '', 'NAME'])
            workbook.save(student_details_file)
            autofit_excel(student_details_file)
        except Exception as e:
            mess._show(title='Error', message=f'Failed to create StudentDetails file: {e}')
            return

    # Load workbook to determine next serial (robustly) for registration serial
    try:
        df_existing = pd.read_excel(student_details_file)
        df_existing = df_existing.dropna(how='all')
        if 'SERIAL NO.' in df_existing.columns:
            numeric_serials = df_existing['SERIAL NO.'].apply(lambda x: int(x) if (pd.notna(x) and str(x).isdigit()) else None).dropna().astype(int)
            if len(numeric_serials) == 0:
                serial = 1
            else:
                serial = int(numeric_serials.max()) + 1
        else:
            serial = 1
    except Exception:
        # fallback
        try:
            wb_tmp = load_workbook(student_details_file)
            sheet_tmp = wb_tmp.active
            serial = sheet_tmp.max_row
            if serial <= 1:
                serial = 1
        except Exception:
            serial = 1

    Id = txt.get().strip()
    name = txt2.get().strip()

    if not Id.isdigit():
        message.configure(text="ID must be numeric.")
        return
    if not name.replace(" ", "").isalpha():
        message.configure(text="Enter a valid name (letters and spaces only).")
        return

    # Create user folder for training images
    safe_name = name.replace(" ", "_")
    user_folder = os.path.join("TrainingImage", f"{safe_name}_{Id}")
    assure_path_exists(user_folder)

    cam = cv2.VideoCapture(0)
    if not cam.isOpened():
        message.configure(text="Failed to access camera.")
        return

    detector = cv2.CascadeClassifier("haarcascade_frontalface_default.xml")
    sampleNum = 0

    try:
        while True:
            ret, img = cam.read()
            if not ret:
                break
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces = detector.detectMultiScale(gray, 1.3, 5)

            for (x, y, w, h) in faces:
                sampleNum += 1
                face_color = img[y:y + h, x:x + w]
                filename = f"{name}.{serial}.{Id}.{sampleNum}.jpg"
                cv2.imwrite(os.path.join(user_folder, filename), face_color)
                cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.imshow('Taking Images (Press Q to quit)', img)

            key = cv2.waitKey(100) & 0xFF
            if key == ord('q') or key == ord('Q') or sampleNum >= 100:
                break
    finally:
        cam.release()
        cv2.destroyAllWindows()

    # Append student details to Excel file using pandas
    try:
        df_row = pd.DataFrame([[serial, int(Id), name]], columns=['SERIAL NO.', 'ID', 'NAME'])
        try:
            df_all = pd.read_excel(student_details_file)
            df_all = df_all.dropna(how='all')
            df_all = pd.concat([df_all, df_row], ignore_index=True)
        except Exception:
            df_all = df_row
        df_all.to_excel(student_details_file, index=False)
        autofit_excel(student_details_file)
    except Exception as e:
        mess._show(title='Error', message=f'Failed to save student details: {e}')
        return

    # ✅ Update counter
    update_registration_counter()
    message1.configure(text="1)Take Images  >>>  2)Save Profile (Now click Save Profile to train)")

########################################################################################

def TrainImages():
    if not check_haarcascadefile():
        return
    assure_path_exists("TrainingImageLabel")

    try:
        recognizer = cv2.face.LBPHFaceRecognizer_create()
    except AttributeError:
        message.configure(text="LBPH Recognizer not available. Please install opencv-contrib-python.")
        return

    faces, ID = getImagesAndLabels("TrainingImage")

    if len(faces) == 0 or len(ID) == 0:
        mess._show(title='No Registrations', message='Please register someone first!')
        return

    try:
        recognizer.train(faces, np.array(ID))
        recognizer.save(os.path.join("TrainingImageLabel", "Trainer.yml"))
        message1.configure(text="Profile trained and saved successfully.")
    except Exception as e:
        message.configure(text=f"Training failed: {e}")
        return

    # ✅ Update counter
    update_registration_counter()

############################################################################################3

def getImagesAndLabels(path):
    faces = []
    Ids = []
    # Use os.walk to go through all subdirectories
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.lower().endswith(("jpeg", "jpg", "png")):
                imagePath = os.path.join(root, file)
                # Loading the image and converting it to gray scale
                try:
                    pilImage = Image.open(imagePath).convert('L')
                    imageNp = np.array(pilImage, 'uint8')
                except Exception:
                    continue
                # getting the Id from the image filename
                try:
                    ID = int(os.path.split(imagePath)[-1].split(".")[2])
                except Exception:
                    continue
                faces.append(imageNp)
                Ids.append(ID)
    return faces, Ids

###########################################################################################

def TrackImages():
    if not check_haarcascadefile():
        return
    assure_path_exists("Attendance/")
    assure_path_exists("StudentDetails/")

    # Clear Treeview
    for k in tv.get_children():
        tv.delete(k)

    try:
        recognizer = cv2.face.LBPHFaceRecognizer_create()
    except Exception:
        mess._show(title='Error', message='LBPH recognizer not available. Please install opencv-contrib-python.')
        return

    trainer_path = os.path.join("TrainingImageLabel", "Trainer.yml")
    if not os.path.isfile(trainer_path):
        mess._show(title='Data Missing', message='Please click on Save Profile to reset data!!')
        return

    recognizer.read(trainer_path)
    faceCascade = cv2.CascadeClassifier("haarcascade_frontalface_default.xml")
    cam = cv2.VideoCapture(0)
    font = cv2.FONT_HERSHEY_SIMPLEX

    details_path = student_details_file
    if not os.path.isfile(details_path):
        mess._show(title='Details Missing', message='Students details are missing, please check!')
        cam.release()
        cv2.destroyAllWindows()
        return

    try:
        df = pd.read_excel(details_path)
    except Exception:
        df = pd.DataFrame(columns=['SERIAL NO.', 'ID', 'NAME'])

    start_time = time.time()
    max_duration = 5  # seconds
    attendance = None

    while True:
        ret, im = cam.read()
        if not ret:
            break
        gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
        faces = faceCascade.detectMultiScale(gray, 1.2, 5)
        for (x, y, w, h) in faces:
            cv2.rectangle(im, (x, y), (x + w, y + h), (225, 0, 0), 2)
            try:
                serial_pred, conf = recognizer.predict(gray[y:y + h, x:x + w])
            except Exception:
                serial_pred, conf = -1, 100

            if conf < 50:
                ts = time.time()
                date_str = datetime.datetime.fromtimestamp(ts).strftime('%d-%m-%Y')
                timeStamp = datetime.datetime.fromtimestamp(ts).strftime('%I:%M:%S %p')
                try:
                    student_row = df.loc[df['ID'] == serial_pred]
                    serial_no = str(student_row['SERIAL NO.'].values[0])
                    student_id = str(student_row['ID'].values[0])
                    student_name = str(student_row['NAME'].values[0])
                    attendance = [serial_no, student_id, student_name, str(date_str), str(timeStamp)]
                    bb = student_name
                except Exception:
                    attendance = None
                    bb = "Unknown"
            else:
                bb = 'Unknown'
            cv2.putText(im, str(bb), (x, y + h), font, 1, (255, 255, 255), 2)

        cv2.imshow('Taking Attendance (Press Q to quit)', im)

        key = cv2.waitKey(1) & 0xFF
        if key in [ord('q'), ord('Q')]:
            break

        if time.time() - start_time >= max_duration:
            break

    # Save attendance to a single persistent Attendance.xlsx (never reset)
    ts = time.time()
    date_str = datetime.datetime.fromtimestamp(ts).strftime('%d-%m-%Y')
    attendance_folder = "Attendance"
    attendance_file = os.path.join(attendance_folder, "Attendance.xlsx")
    assure_path_exists(attendance_folder)

    if attendance is None:
        mess._show(title='No Entry', message='No valid attendance was captured.')
    else:
        # Create or open the workbook, ensure header
        if os.path.isfile(attendance_file):
            try:
                wb = load_workbook(attendance_file)
                ws = wb.active
            except Exception:
                # if corrupt or unreadable, recreate
                wb = Workbook()
                ws = wb.active
                ws.append(['S.No', 'ID', 'Name', 'Date', 'Time'])
        else:
            wb = Workbook()
            ws = wb.active
            ws.append(['S.No', 'ID', 'Name', 'Date', 'Time'])

        # Determine next serial number (persistent across sessions)
        try:
            if ws.max_row > 1:
                last_serial = ws.cell(row=ws.max_row, column=1).value
                try:
                    next_serial = int(last_serial) + 1
                except Exception:
                    # fallback if last value isn't int
                    # scan upward for last numeric serial
                    next_serial = 1
                    for r in range(ws.max_row, 0, -1):
                        val = ws.cell(row=r, column=1).value
                        try:
                            if val is not None:
                                next_serial = int(val) + 1
                                break
                        except Exception:
                            continue
                serial_to_write = next_serial
            else:
                serial_to_write = 1
        except Exception:
            serial_to_write = 1

        # Append attendance row (use student ID and name from recognized data)
        try:
            # attendance holds [serial_no_from_students_file, student_id, student_name, date, time]
            _, student_id, student_name, date_val, time_val = attendance
            ws.append([serial_to_write, student_id, student_name, date_val, time_val])
            wb.save(attendance_file)
            autofit_excel(attendance_file)
        except Exception as e:
            mess._show(title='Error', message=f'Failed to save attendance: {e}')
            try:
                wb.save(attendance_file)
            except Exception:
                pass
            cam.release()
            cv2.destroyAllWindows()
            return

        # Load and show attendance in Treeview (latest first)
        try:
            df_att = pd.read_excel(attendance_file)
            # Clear treeview then insert rows (we cleared earlier)
            for _, row in df_att.iterrows():
                try:
                    if pd.notna(row['S.No']) or pd.notna(row['S.No'.upper()]):
                        # handle both header cases if necessary
                        s = row.get('S.No', row.get('S.NO', row.get('S.No.', None)))
                    # safe insertion
                    tv.insert('', 'end', text=row.iloc[0], values=(row.iloc[1], row.iloc[2], row.iloc[3], row.iloc[4]))
                except Exception:
                    vals = list(row)
                    if len(vals) >= 5:
                        tv.insert('', 'end', text=vals[0], values=(vals[1], vals[2], vals[3], vals[4]))
        except Exception:
            pass

    cam.release()
    cv2.destroyAllWindows()

######################################## USED STUFFS ############################################

global key
key = ''

ts = time.time()
date = datetime.datetime.fromtimestamp(ts).strftime('%d-%m-%Y')
day, month, year = date.split("-")

mont = {'01': 'January',
        '02': 'February',
        '03': 'March',
        '04': 'April',
        '05': 'May',
        '06': 'June',
        '07': 'July',
        '08': 'August',
        '09': 'September',
        '10': 'October',
        '11': 'November',
        '12': 'December'
        }

######################################## GUI FRONT-END ###########################################

window = tk.Tk()
window.geometry("1280x720")
window.minsize(1080, 680)
window.resizable(True, False)
window.title("Attendance Studio")
window.configure(background='#eef3f7')

ui_font = 'Segoe UI'
colors = {
    'ink': '#17212b',
    'muted': '#637383',
    'navy': '#15324b',
    'teal': '#0f8b8d',
    'teal_dark': '#0a6668',
    'surface': '#ffffff',
    'line': '#d7e1e8',
    'canvas': '#eef3f7',
    'danger': '#c94c4c',
}

style = ttk.Style(window)
try:
    style.theme_use('clam')
except tk.TclError:
    pass
style.configure('Modern.Treeview', background=colors['surface'], fieldbackground=colors['surface'],
                foreground=colors['ink'], rowheight=30, font=(ui_font, 10), borderwidth=0)
style.configure('Modern.Treeview.Heading', background=colors['navy'], foreground='white',
                font=(ui_font, 10, 'bold'), relief='flat', padding=(8, 8))
style.map('Modern.Treeview', background=[('selected', '#d9eff0')], foreground=[('selected', colors['ink'])])
style.configure('Modern.Vertical.TScrollbar', troughcolor='#e8eef2', background='#a7bbc8', borderwidth=0)

# Load background
if os.path.exists("background_image1.png"):
    try:
        bg_image = Image.open("background_image1.png")
        bg_photo = ImageTk.PhotoImage(bg_image)
        background_label = tk.Label(window, image=bg_photo)
        background_label.place(x=0, y=0, relwidth=1, relheight=1)
    except Exception:
        pass

frame1 = tk.Frame(window, bg=colors['surface'], highlightbackground=colors['line'], highlightthickness=1)
frame1.place(relx=0.05, rely=0.20, relwidth=0.43, relheight=0.75)

frame2 = tk.Frame(window, bg=colors['surface'], highlightbackground=colors['line'], highlightthickness=1)
frame2.place(relx=0.52, rely=0.20, relwidth=0.43, relheight=0.75)

message3 = tk.Label(window, text="Face Recognition Based Attendance Monitoring System",
                    fg=colors['navy'], bg=colors['canvas'], width=55, height=1,
                    font=(ui_font, 24, 'bold'))
message3.place(x=42, y=20, anchor='w')

datef = tk.Label(window, text=day + "-" + mont[month] + "-" + year,
                 fg=colors['muted'], bg=colors['canvas'], width=20, font=(ui_font, 11, 'bold'))
datef.place(relx=0.72, rely=0.065)

clock = tk.Label(window, fg=colors['teal'], bg=colors['canvas'], width=20, font=(ui_font, 11, 'bold'))
clock.place(relx=0.86, rely=0.065)
tick()

head2 = tk.Label(frame2, text="                       For New Registrations                       ",
                 fg="white", bg=colors['teal'], font=(ui_font, 13, 'bold'))
head2.place(x=0, y=-5)

head1 = tk.Label(frame1, text="                       For Already Registered                       ",
                 fg="white", bg=colors['navy'], font=(ui_font, 13, 'bold'))
head1.place(x=0, y=-5)

lbl = tk.Label(frame2, text="Enter ID", width=20, height=1, fg=colors['ink'],
               bg=colors['surface'], font=(ui_font, 11, 'bold'))
lbl.place(x=80, y=55)
txt = tk.Entry(frame2, width=32, fg=colors['ink'], font=(ui_font, 11))
txt.place(x=30, y=88)
txt_warning = tk.Label(frame2, text="", fg=colors['danger'], bg=colors['surface'], font=(ui_font, 9, 'bold'))
txt_warning.place(x=30, y=120)
check_capslock_continuous(txt, txt_warning)

lbl2 = tk.Label(frame2, text="Enter Name", width=20, fg=colors['ink'], bg=colors['surface'],
                font=(ui_font, 11, 'bold'))
lbl2.place(x=80, y=140)
txt2 = tk.Entry(frame2, width=32, fg=colors['ink'], font=(ui_font, 11))
txt2.place(x=30, y=173)
txt2_warning = tk.Label(frame2, text="", fg=colors['danger'], bg=colors['surface'], font=(ui_font, 9, 'bold'))
txt2_warning.place(x=30, y=205)
check_capslock_continuous(txt2, txt2_warning)

message1 = tk.Label(frame2, text="1) Take Images   >   2) Save Profile", bg=colors['surface'],
                    fg=colors['muted'], width=39, height=1, activebackground=colors['surface'],
                    font=(ui_font, 10, 'bold'))
message1.place(x=7, y=230)

message = tk.Label(frame2, text="", bg=colors['surface'], fg=colors['teal'], width=39, height=1,
                   activebackground=colors['surface'], font=(ui_font, 10, 'bold'))
message.place(x=7, y=450)

lbl3 = tk.Label(frame1, text="Attendance", width=20, fg=colors['ink'], bg=colors['surface'],
                height=1, font=(ui_font, 11, 'bold'))
lbl3.place(x=100, y=125)

# Ensure StudentDetails file exists and compute initial count
if not os.path.exists(student_details_file):
    try:
        wb = Workbook()
        ws = wb.active
        ws.title = "Students"
        ws.append(['SERIAL NO.', 'ID', 'NAME'])
        wb.save(student_details_file)
        autofit_excel(student_details_file)
    except Exception:
        pass

res = compute_registration_count()
message.configure(text='Total Registrations till now: ' + str(res))

##################### MENUBAR #################################

menubar = tk.Menu(window, relief='flat', bg=colors['surface'], fg=colors['ink'],
                  activebackground=colors['teal'], activeforeground='white')
filemenu = tk.Menu(menubar, tearoff=0, bg=colors['surface'], fg=colors['ink'],
                   activebackground=colors['teal'], activeforeground='white')
filemenu.add_command(label='Change Password', command=change_pass)
filemenu.add_command(label='Contact Us', command=contact)
filemenu.add_command(label='Exit', command=window.destroy)
menubar.add_cascade(label='Help', font=(ui_font, 10, 'bold'), menu=filemenu)

################## TREEVIEW ATTENDANCE TABLE ####################

tv = ttk.Treeview(frame1, height=13, columns=('id', 'name', 'date', 'time'), style='Modern.Treeview')

tv.column('#0', width=60)
tv.column('id', width=80, anchor=tk.CENTER)
tv.column('name', width=130, anchor=tk.CENTER)
tv.column('date', width=130, anchor=tk.CENTER)
tv.column('time', width=130, anchor=tk.CENTER)

tv.grid(row=2, column=0, padx=(0, 0), pady=(150, 0), columnspan=4)

tv.heading('#0', text='Serial No.')
tv.heading('id', text='ID')
tv.heading('name', text='Name')
tv.heading('date', text='Date')
tv.heading('time', text='Time')
###################### SCROLLBAR ################################

scroll = ttk.Scrollbar(frame1, orient='vertical', command=tv.yview)
scroll.grid(row=2, column=4, padx=(0, 100), pady=(150, 0), sticky='ns')
tv.configure(yscrollcommand=scroll.set)

# Horizontal scrollbar to Treeview
scroll_x = ttk.Scrollbar(frame1, orient='horizontal', command=tv.xview)
scroll_x.grid(row=3, column=0, pady=(0, 20), padx=(0, 100), sticky='ew')
tv.configure(xscrollcommand=scroll_x.set)

###################### BUTTONS ##################################
clearButton = tk.Button(frame2, text="Clear", command=clear, fg="black", bg="#ff7221",
                        width=11, activebackground="white", font=('comic', 11, ' bold '))
clearButton.place(x=335, y=86)
clearButton2 = tk.Button(frame2, text="Clear", command=clear2, fg="black", bg="#ff7221",
                         width=11, activebackground="white", font=('comic', 11, ' bold '))
clearButton2.place(x=335, y=172)
takeImg = tk.Button(frame2, text="Take Images", command=TakeImages, fg="white", bg="#6d00fc",
                    width=34, height=1, activebackground="white", font=('comic', 15, ' bold '))
takeImg.place(x=30, y=300)
trainImg = tk.Button(frame2, text="Save Profile", command=psw, fg="white", bg="#6d00fc",
                     width=34, height=1, activebackground="white", font=('comic', 15, ' bold '))
trainImg.place(x=30, y=380)
trackImg = tk.Button(frame1, text="Take Attendance", command=TrackImages, fg="black", bg="#3ffc00",
                     width=13, height=1, activebackground="white", font=('comic', 12, ' bold '))
trackImg.place(x=160, y=85)
quitWindow = tk.Button(frame1, text="Quit", command=window.destroy, fg="black", bg="#eb4600",
                       width=35, height=1, activebackground="white", font=('comic', 15, ' bold '))
quitWindow.place(x=30, y=460)

# Email Section
email_domains = ["gmail.com", "yahoo.com", "hotmail.com"]
recipient_email_label = tk.Label(frame1, text="Recipient's Email", width=31, fg="black", bg="pink",
                                  font=('comic', 9, ' bold '))
recipient_email_label.place(x=6, y=30)
recipient_email_entry = tk.Entry(frame1, width=20, fg="black", bg="#d3f0dc", font=('comic', 15, ' bold '))
recipient_email_entry.place(x=5, y=50)

from_email_label = tk.Label(frame1, text="Sender's Email", width=31, fg="black", bg="pink",
                            font=('comic', 9, ' bold '))
from_email_label.place(x=6, y=520)
from_email_entry = tk.Entry(frame1, width=20, fg="black", bg="#d3f0dc", font=('comic', 15, ' bold '))
from_email_entry.place(x=5, y=540)

password_label = tk.Label(frame1, text="Sender's Email Password", width=31, fg="black", bg="pink",
                          font=('comic', 9, ' bold '))
password_label.place(x=261, y=520)
password_entry = tk.Entry(frame1, width=20, fg="black", bg="#d3f0dc", font=('comic', 15, ' bold '), show='*')
password_entry.place(x=260, y=540)
password_warning = tk.Label(frame1, text="", fg="red", bg="#c79cff", font=('comic', 6, ' bold '))
password_warning.place(x=260, y=503)
check_capslock_continuous(password_entry, password_warning)

# Toggle visibility for the sender's email password
def toggle_password_visibility():
    if password_entry.cget('show') == '':
        password_entry.config(show='*')
        password_toggle_btn.config(text='Show')
    else:
        password_entry.config(show='')
        password_toggle_btn.config(text='Hide')

password_toggle_btn = tk.Button(frame1, text='Show', command=toggle_password_visibility, width=3, font=('comic', 7))
password_toggle_btn.place(x=455, y=520)

# Add domain dropdown menu
domain_label = tk.Label(frame1, text="Domain:", width=20, fg="black", bg="pink",
                        font=('comic', 9, ' bold '))
domain_label.place(x=250, y=30)
domain_var = tk.StringVar(frame1)
domain_var.set(email_domains[0])
domain_dropdown = tk.OptionMenu(frame1, domain_var, *email_domains)
domain_dropdown.config(width=15, font=('comic', 9, ' bold '))
domain_dropdown.place(x=250, y=50)

# Add "@" symbol
at_symbol_label = tk.Label(frame1, text="@", width=2, fg="black", bg="white",
                           font=('comic', 10, ' bold '))
at_symbol_label.place(x=230, y=50)

# ✅ Email Sending Function (uses single Attendance.xlsx)
def send_email():
    recipient_email = recipient_email_entry.get().strip()
    selected_domain = domain_var.get().strip()

    if not recipient_email:
        mess._show(title='Error', message='Please enter a recipient email address.')
        return

    # Concatenate selected domain with recipient's email address if not already present
    if '@' not in recipient_email:
        recipient_email = recipient_email + "@" + selected_domain

    from_email = from_email_entry.get().strip()
    if from_email and '@' not in from_email:
        # append selected domain to sender if user typed only username
        from_email = from_email + "@" + selected_domain

    password = password_entry.get()

    if not from_email or not password:
        mess._show(title='Error', message='Please enter sender email and password.')
        return

    # Single attendance file
    attendance_file = os.path.join("Attendance", "Attendance.xlsx")
    if not os.path.isfile(attendance_file):
        mess._show(title='Error', message=f'Attendance file not found: {attendance_file}')
        return

    try:
        msg = MIMEMultipart()
        msg['From'] = from_email
        msg['To'] = recipient_email
        msg['Subject'] = "Attendance Report"

        body = "Please find attached the attendance report."
        msg.attach(MIMEText(body, 'plain'))

        with open(attendance_file, "rb") as attachment:
            part = MIMEBase('application', 'vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f"attachment; filename={os.path.basename(attendance_file)}")
            msg.attach(part)

        # Send the email via Gmail SMTP (works for any SMTP server with modifications)
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(from_email, password)
        server.sendmail(from_email, recipient_email, msg.as_string())
        server.quit()
        mess._show(title='Success', message='Attendance report sent successfully.')
    except Exception as e:
        mess._show(title='Error', message=f'Failed to send email. ({e})')

# Send email button
send_email_button = tk.Button(frame1, text="Send Attendance", command=send_email, fg="black",
                              bg="sky blue", width=13, activebackground="white",
                              font=('comic', 8, ' bold '))
send_email_button.place(x=400, y=50)

# ✅ Delete functions (updated for single Attendance.xlsx)
def delete_registration_xlsx():
    registration_xlsx_path = student_details_file
    if os.path.exists(registration_xlsx_path):
        try:
            os.remove(registration_xlsx_path)
            mess.showinfo("Success", "Registration XLSX file deleted successfully.")
            # Recreate empty registration file
            wb = Workbook()
            ws = wb.active
            ws.title = "Students"
            ws.append(['SERIAL NO.', 'ID', 'NAME'])
            wb.save(registration_xlsx_path)
            autofit_excel(registration_xlsx_path)
            update_registration_counter()
        except Exception as e:
            mess.showinfo("Error", f"Failed to delete Registration XLSX: {e}")
    else:
        mess.showinfo("Error", "Registration XLSX file not found.")

def delete_attendance_xlsx():
    attendance_xlsx_path = os.path.join("Attendance", "Attendance.xlsx")
    if os.path.exists(attendance_xlsx_path):
        try:
            os.remove(attendance_xlsx_path)
            mess.showinfo("Success", f"Attendance XLSX file deleted successfully.")
        except Exception as e:
            mess.showinfo("Error", f"Failed to delete attendance: {e}")
    else:
        mess.showinfo("Error", f"Attendance XLSX file not found.")

delete_registration_button = tk.Button(frame1, text="Delete Registration XLSX", command=delete_registration_xlsx,
                                       fg="white", bg="red", width=19, font=('comic', 8, 'bold'))
delete_registration_button.place(x=5, y=85)

delete_attendance_button = tk.Button(frame1, text="Delete Attendance XLSX", command=delete_attendance_xlsx,
                                     fg="white", bg="red", width=19, font=('comic', 8, 'bold'))
delete_attendance_button.place(x=320, y=85)

def delete_registered_images():
    folder_path = "TrainingImage/"
    if os.path.exists(folder_path):
        try:
            shutil.rmtree(folder_path)
            mess.showinfo("Success", "Registered images deleted successfully.")
        except Exception as e:
            mess.showinfo("Error", f"Failed to delete registered images: {e}")
    else:
        mess.showinfo("Error", "TrainingImage folder not found.")

delete_images_button = tk.Button(frame1, text="Delete Registered Images", command=delete_registered_images,
                                 fg="white", bg="red", width=20, font=('comic', 8, 'bold'))
delete_images_button.place(x=320, y=115)

def apply_modern_control_style(container):
    for child in container.winfo_children():
        if isinstance(child, tk.Frame):
            child.configure(bg=colors['surface'])
            apply_modern_control_style(child)
        elif isinstance(child, tk.Label):
            if child not in (head1, head2):
                child.configure(bg=colors['surface'], fg=colors['ink'])
        elif isinstance(child, tk.Entry):
            child.configure(bg='#f8fbfc', fg=colors['ink'], insertbackground=colors['teal'],
                            relief='solid', bd=1, highlightthickness=0)
        elif isinstance(child, tk.Button):
            label = child.cget('text')
            if label in ('Take Images', 'Save Profile', 'Take Attendance', 'Send Attendance'):
                child.configure(bg=colors['teal'], fg='white', activebackground=colors['teal_dark'],
                                 activeforeground='white', relief='flat', bd=0, cursor='hand2')
            elif label.startswith('Delete') or label == 'Quit':
                child.configure(bg=colors['danger'], fg='white', activebackground='#a63c3c',
                                 activeforeground='white', relief='flat', bd=0, cursor='hand2')
            else:
                child.configure(bg='#e8eef2', fg=colors['ink'], activebackground='#d9e5ea',
                                 relief='flat', bd=0, cursor='hand2')

apply_modern_control_style(frame1)
apply_modern_control_style(frame2)
tv.configure(style='Modern.Treeview')

##################### END ######################################
window.configure(menu=menubar)
window.mainloop()
