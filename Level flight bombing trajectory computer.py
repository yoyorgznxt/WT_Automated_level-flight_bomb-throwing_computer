import pytesseract
import mss
import time
import math
import threading
import keyboard
from PIL import Image
import re
import tkinter as tk
from tkinter import font

# ====================== 配置区域 ======================
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# OCR识别区域
HEIGHT_REGION = {"top": 130, "left": 233, "width": 95, "height": 38}  # 雷达高度（离地高度）
SPEED_REGION  = {"top": 71, "left": 260, "width": 56, "height": 30}   # 速度
ALTITUDE_REGION = {"top": 101, "left": 247, "width": 78, "height": 34}  # 实际高度（海拔高度）

UPDATE_INTERVAL = 0.2
DEBUG_MODE = True  # 开启调试模式，可以看到OCR识别结果（这两行没用，不用管）
# ======================================================

BOMB_PARAMS = {
    "m": 500.76,
    "S": 0.1787,
    "Cd": 0.042,
    "g": 9.81
}

class BombCalculator:
    def __init__(self):
        self.running = True
        self.radar_height = 0.0  # 雷达高度（离地高度）
        self.altitude = 0.0      # 实际高度（海拔高度）
        self.speed = 0.0
        self.slant = 0.0

        # 悬浮窗口：修改标题，加高窗口以容纳更多信息
        self.root = tk.Tk()
        self.root.title("平飞投弹计算器")
        self.root.geometry("300x160")  # 增加高度以显示实际高度
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.9)
        
        # 监听窗口大小变化
        self.root.bind('<Configure>', self.on_window_resize)

        # 使用Frame来组织布局
        self.main_frame = tk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建Text组件来支持多色文本
        self.text_widget = tk.Text(self.main_frame, font=("Microsoft YaHei", 12, "bold"),
                                  bg=self.root.cget('bg'), relief='flat', borderwidth=0, state=tk.DISABLED)
        self.text_widget.pack(fill=tk.BOTH, expand=True)
        
        # 定义颜色标签
        self.text_widget.tag_configure("red", foreground="red", font=("Microsoft YaHei", 12, "bold"))
        self.text_widget.tag_configure("blue", foreground="blue", font=("Microsoft YaHei", 12, "bold"))

    def get_air_density(self, altitude):
        """使用实际高度（海拔高度）计算空气密度"""
        if altitude < 11000:
            T = 288.15 - 0.0065 * altitude
            p = 101325 * (T / 288.15) ** 5.25588
            rho = p / (287.058 * T)
            return rho
        return 0.3639

    # ===================== 稳定版OCR，不破坏数字 =====================
    def ocr_read(self, region, label=""):
        try:
            with mss.mss() as sct:
                img = sct.grab(region)
                im = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")

                # 极轻量：只转灰度，不破坏字体
                im = im.convert('L')

                cfg = r'--psm 6 -c tessedit_char_whitelist=0123456789.'
                text = pytesseract.image_to_string(im, config=cfg)
                nums = re.findall(r'\d+\.?\d*', text)
                
                result = float(nums[0]) if nums else 0.0
                
                # 调试输出
                if DEBUG_MODE:
                    print(f"[DEBUG] {label}: 区域{region}, 识别文本:'{text.strip()}', 结果:{result}")
                
                return result
        except Exception as e:
            if DEBUG_MODE:
                print(f"[ERROR] {label}: {str(e)}")
            return 0.0

    def calculate_slant(self, radar_height, altitude, speed_kmh):
        """
        计算斜距
        radar_height: 雷达高度（离地高度）- 用于其他计算
        altitude: 实际高度（海拔高度）- 用于空气密度计算
        """
        if radar_height < 10 or speed_kmh < 10:
            return 0.0

        v0 = speed_kmh / 3.6
        m = BOMB_PARAMS["m"]
        S = BOMB_PARAMS["S"]
        Cd = BOMB_PARAMS["Cd"]
        g = BOMB_PARAMS["g"]

        # 使用实际高度计算空气密度
        rho = self.get_air_density(altitude)

        dt = 0.01
        x, y = 0.0, radar_height  # 使用雷达高度作为初始垂直坐标
        vx, vy = v0, 0.0

        while y > 0:
            v = math.hypot(vx, vy)
            if v < 0.1:
                break

            f_drag = 0.5 * rho * Cd * S * v**2
            ax = -f_drag * vx / (v * m)
            ay = -g - f_drag * vy / (v * m)

            vx += ax * dt
            vy += ay * dt
            x += vx * dt
            y += vy * dt

        return math.hypot(x, radar_height)  # 使用雷达高度计算斜距

    def update_loop(self):
        while self.running:
            self.radar_height = self.ocr_read(HEIGHT_REGION, "雷达高度")
            self.altitude = self.ocr_read(ALTITUDE_REGION, "实际高度")
            self.speed = self.ocr_read(SPEED_REGION, "速度")
            self.slant = self.calculate_slant(self.radar_height, self.altitude, self.speed)
            time.sleep(UPDATE_INTERVAL)

    def update_window(self):
        while self.running:
            # 更新文本显示
            self.update_display_text()
            self.root.update()
            time.sleep(0.05)

    def update_display_text(self):
        # 准备文本内容 - 重新排列，使关键数据紧密排列
        txt = (f"雷达高度:{self.radar_height:4.0f}m\n"
               f"实际高度:{self.altitude:4.0f}m\n"
               f"速度:{self.speed:4.0f}km/h\n"
               f"斜距L:{self.slant:6.0f}m\n"
               f"作者：b站 真理喀秋莎6666")
        
        # 重新配置Text组件
        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.delete(1.0, tk.END)
        self.text_widget.insert(tk.END, txt)
        
        # 应用颜色标签 - 关键数据紧密排列
        lines = txt.split('\n')
        for i, line in enumerate(lines, start=1):
            if line.startswith("斜距L:"):
                start_pos = f"{i}.0"
                end_pos = f"{i}.{len(line)}"
                self.text_widget.tag_add("red", start_pos, end_pos)
            elif line.startswith("雷达高度:"):
                start_pos = f"{i}.0"
                end_pos = f"{i}.{len(line)}"
                self.text_widget.tag_add("blue", start_pos, end_pos)
        
        self.text_widget.config(state=tk.DISABLED)

    def on_window_resize(self, event=None):
        # 防止在初始化时重复调用
        if hasattr(self, 'root') and event.widget == self.root:
            # 获取当前窗口大小
            width = self.root.winfo_width()
            height = self.root.winfo_height()
            
            # 计算合适的字体大小
            base_size = max(8, min(width//18, height//12))
            
            # 应用新字体大小
            new_font = ("Microsoft YaHei", int(base_size), "bold")
            self.text_widget.config(font=new_font)
            # 同时更新颜色标签的字体
            self.text_widget.tag_configure("red", foreground="red", font=new_font)
            self.text_widget.tag_configure("blue", foreground="blue", font=new_font)

    def start(self):
        # 更新控制台打印信息
        print("=== 平飞投弹计算器 ===")
        print("调试模式已开启，OCR识别结果将显示在控制台")
        print("请根据调试输出调整ALTITUDE_REGION参数")
        print("实际高度显示区域坐标格式: {\"top\": Y, \"left\": X, \"width\": W, \"height\": H}")
        threading.Thread(target=self.update_loop, daemon=True).start()
        threading.Thread(target=self.update_window, daemon=True).start()
        self.root.protocol("WM_DELETE_WINDOW", lambda: (setattr(self, 'running', False), self.root.destroy()))
        self.root.mainloop()
        print("\n已退出")

if __name__ == "__main__":
    BombCalculator().start()