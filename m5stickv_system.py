import lcd
import machine
import sys

from Maix import GPIO
from board import board_info
from fpioa_manager import fm

import image
# import gc
import time
import resource
import config

from my_pmu import AXP192
from app_launcher import LauncherApp
from framework import NeedRebootException


class M5StickVSystem:
    def __init__(self):
        self.pmu = AXP192()
        self.pmu.setScreenBrightness(0)
        self.pmu.set_on_pressed_listener(self.on_pek_button_pressed)
        self.pmu.set_on_long_pressed_listener(self.on_pek_button_long_pressed)
        self.pmu.set_system_periodic_task(self.system_periodic_task)
        self.app_stack = []

        lcd.init()
        self.pmu.setScreenBrightness(0)
        lcd.rotation(2)  # Rotate the lcd 180deg
        # set brightness to zero before first draw to avoid flower screen
        self.pmu.setScreenBrightness(0)

        self.home_button = None
        self.top_button = None
        self.led_w = None
        self.led_r = None
        self.led_g = None
        self.led_b = None
        self.spk_sd = None
        self.is_handling_irq = False
        self.init_fm()

        self.is_drawing_dirty = False
        self.is_boot_complete_first_draw = True
        self.show_provision()
        self.navigate(LauncherApp(self))

    def show_provision(self):
        img = image.Image(resource.provision_image_path)
        lcd.display(img)
        del img
        lcd.draw_string(54, 6,
                        "NEXT", lcd.RED, lcd.BLACK)
        lcd.draw_string(168, 6,
                        "ENTER", lcd.RED, lcd.BLACK)
        lcd.draw_string(152, lcd.height() - 18,
                        "BACK/POWER", lcd.RED, lcd.BLACK)
        lcd.draw_string(21, lcd.height() - 18,
                        "StickV Computer", lcd.WHITE, lcd.BLACK)
        self.check_restore_brightness()
        self.wait_event()

    def button_irq(self, gpio, optional_pin_num=None):
        print("button_irq start:", gpio, optional_pin_num)
        # Notice: optional_pin_num exist in older firmware
        if self.is_handling_irq:
            print("is_handing_irq, ignore")
            return
        self.is_handing_irq = True
        value = gpio.value()
        state = "released" if value else "pressed"
        # msg = {"type": "key_event", "gpio": gpio, "state": state}
        print("button_irq:", gpio, optional_pin_num, state)
        if self.home_button is gpio:
            self.on_home_button_changed(state)
        elif self.top_button is gpio:
            self.on_top_button_changed(state)
        self.is_handing_irq = False
        print("button_irq end:", gpio, optional_pin_num, state)
        #gpio.irq(self.button_irq, GPIO.IRQ_BOTH, GPIO.WAKEUP_NOT_SUPPORT, 7)

    # noinspection SpellCheckingInspection
    def init_fm(self):
        # home button
        fm.register(board_info.BUTTON_A, fm.fpioa.GPIOHS21)
        # PULL_UP is required here!
        self.home_button = GPIO(GPIO.GPIOHS21, GPIO.IN, GPIO.PULL_UP)
        # self.home_button.irq(self.button_irq, GPIO.IRQ_BOTH,
        #                      GPIO.WAKEUP_NOT_SUPPORT, 7)

        if self.home_button.value() == 0:  # If don't want to run the demo
            sys.exit()

        # top button
        fm.register(board_info.BUTTON_B, fm.fpioa.GPIOHS22)
        # PULL_UP is required here!
        self.top_button = GPIO(GPIO.GPIOHS22, GPIO.IN, GPIO.PULL_UP)
        # self.top_button.irq(self.button_irq, GPIO.IRQ_BOTH,
        #                     GPIO.WAKEUP_NOT_SUPPORT, 7)
        return  # TODO: fix me
        fm.register(board_info.LED_W, fm.fpioa.GPIO3)
        self.led_w = GPIO(GPIO.GPIO3, GPIO.OUT)
        self.led_w.value(1)  # RGBW LEDs are Active Low

        fm.register(board_info.LED_R, fm.fpioa.GPIO4)
        self.led_r = GPIO(GPIO.GPIO4, GPIO.OUT)
        self.led_r.value(1)  # RGBW LEDs are Active Low

        fm.register(board_info.LED_G, fm.fpioa.GPIO5)
        self.led_g = GPIO(GPIO.GPIO5, GPIO.OUT)
        self.led_g.value(1)  # RGBW LEDs are Active Low

        fm.register(board_info.LED_B, fm.fpioa.GPIO6)
        self.led_b = GPIO(GPIO.GPIO6, GPIO.OUT)
        self.led_b.value(1)  # RGBW LEDs are Active Low

        fm.register(board_info.SPK_SD, fm.fpioa.GPIO0)
        self.spk_sd = GPIO(GPIO.GPIO0, GPIO.OUT)
        self.spk_sd.value(1)  # Enable the SPK output

        fm.register(board_info.SPK_DIN, fm.fpioa.I2S0_OUT_D1)
        fm.register(board_info.SPK_BCLK, fm.fpioa.I2S0_SCLK)
        fm.register(board_info.SPK_LRCLK, fm.fpioa.I2S0_WS)

    def invalidate_drawing(self):
        print("invalidate_drawing")
        self.is_drawing_dirty = True

    def run(self):
        try:
            self.run_inner()
        except Exception as e:
            import uio
            string_io = uio.StringIO()
            sys.print_exception(e, string_io)
            s = string_io.getvalue()
            print("showing blue screen:", s)
            lcd.clear(lcd.BLUE)
            msg = "** " + str(e)
            chunks, chunk_size = len(msg), 29
            msg_lines = [msg[i:i+chunk_size]
                         for i in range(0, chunks, chunk_size)]
            # "A problem has been detected and windows has been shut down to prevent damange to your m5stickv :)"
            lcd.draw_string(
                1, 1, "A problem has been detected and windows", lcd.WHITE, lcd.BLUE)
            lcd.draw_string(
                1, 1 + 5 + 16, "Technical information:", lcd.WHITE, lcd.BLUE)
            current_y = 1 + 5 + 16 * 2
            for line in msg_lines:
                lcd.draw_string(1, current_y, line, lcd.WHITE, lcd.BLUE)
                current_y += 16
                if current_y >= lcd.height():
                    break
            lcd.draw_string(1, current_y, s, lcd.WHITE, lcd.BLUE)
            lcd.draw_string(
                1, lcd.height() - 17, "Will reboot after 10 seconds..", lcd.WHITE, lcd.BLUE)
            time.sleep(10)
            machine.reset()

    def wait_event(self):
        """key event or view invalidate event"""
        print("wait for all key release")
        while self.home_button.value() == 0 or self.top_button.value() == 0:
            pass
        print("key released, now wait for a event")
        while self.home_button.value() == 1 and self.top_button.value() == 1 and not self.is_drawing_dirty:
            pass
        print("some event arrived")
        if self.is_drawing_dirty:
            print("drawing dirty event")
            return ("drawing", "dirty")
        elif self.home_button.value() == 0:
            print("home_button pressed")
            return (self.home_button, "pressed")
            self.on_home_button_changed("pressed")
        elif self.top_button.value() == 0:
            print("top_button pressed")
            return (self.top_button, "pressed")
            self.on_top_button_changed("pressed")
        else:
            return None

    def check_restore_brightness(self):
        if self.is_boot_complete_first_draw:
            self.is_boot_complete_first_draw = False
            self.pmu.setScreenBrightness(
                config.get_brightness())  # 7-15 is ok, normally 8

    def run_inner(self):
        while True:
            if self.is_drawing_dirty:
                print("drawing is dirty")
                self.is_drawing_dirty = False
                current_app = self.get_current_app()
                # print("before on_draw() of", current_app, "free memory:", gc.mem_free())
                print("current_app.on_draw() start")
                current_app.on_draw()
                print("current_app.on_draw() end")
                # print("on_draw() of", current_app, "called, free memory:", gc.mem_free())
                # this gc is to avoid: "core dump: misaligned load" error
                # print("after gc.collect(), free memory:", gc.mem_free())
                self.check_restore_brightness()
                # print("sleep_ms for 1ms")
                # time.sleep_ms(1)
                # print("sleep_ms for 1ms end")
            else:
                event_info = self.wait_event()
                if event_info is not None and len(event_info) == 2:
                    event = event_info[0]
                    state = event_info[1]
                    if event == self.home_button:
                        self.on_home_button_changed(state)
                    elif event == self.top_button:
                        self.on_top_button_changed(state)

    def navigate(self, app):
        self.app_stack.append(app)
        self.invalidate_drawing()

    def navigate_back(self):
        if len(self.app_stack) > 0:
            self.app_stack.pop()
        self.invalidate_drawing()

    def get_current_app(self):
        return self.app_stack[-1] if len(self.app_stack) > 0 else None

    def on_pek_button_pressed(self, axp):
        # treat short press as navigate back
        print("on_pek_button_pressed", axp)
        handled = False
        current_app = self.get_current_app()
        if current_app:
            try:
                handled = current_app.on_back_pressed()
            except NeedRebootException:
                machine.reset()
        if not handled:
            print("on_back_pressed() not handled, exit current app")
            self.navigate_back()

    def system_periodic_task(self, axp):
        current = self.get_current_app()
        if current:
            current.app_periodic_task()

    # noinspection PyMethodMayBeStatic
    def on_pek_button_long_pressed(self, axp):
        print("on_pek_button_long_pressed", axp)
        axp.setEnterSleepMode()

    def on_home_button_changed(self, state):
        print("on_home_button_changed", state)
        self.get_current_app().on_home_button_changed(state)

    def on_top_button_changed(self, state):
        print("on_top_button_changed", state)
        self.get_current_app().on_top_button_changed(state)
