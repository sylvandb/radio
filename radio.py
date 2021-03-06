#!/usr/bin/python
# -*- coding: utf-8 -*-
# vim: ts=2 sts=2 sw=2 et si
#
# Internet radio for Raspberry Pi
# by sdb
#
# Based on https://tinkerthon.de/2013/04/internet-radio-mit-raspberrypi-2-zeiligem-rgb-lcd-und-5-tasten/
# Copyright (c) 2013 Olav Schettler
# Open source. MIT license
#
# Based on mpd/mpc and the Character LCD Plate by Adafruit
#
# The basic navigation code is based on lcdmenu.py by Alan Aufderheide


import Adafruit_CharLCD as LCD
import subprocess
import signal
from time import strftime, sleep
try:
	from unidecode import unidecode
except ImportError:
	unidecode = lambda f: f


DEBUG = 0
IDLE_SECS = 180
TIME_FORMAT = '%Y.%m.%d %H:%M:%S'




class Locking_CharLCDPlate(LCD.Adafruit_CharLCDPlate):

  import onlyone as _locker

  def __init__(self, *args, **kwargs):
    self._lockname = 'i2c-1-20'
    self._locker.running(name=self._lockname)
    super(Locking_CharLCDPlate, self).__init__(*args, **kwargs)

  def __del__(self):
    self._locker.done(name=self._lockname)




class BaseNode(object):
  '''
  Base class for nodes in a hierarchical navigation tree
  '''
  mark = ' '
  text = 'Base'
  parent = None

  def __repr__(self):
    return 'node: ' + str(self.text)

  def texttrunc(self, *args):
    return self.text


class Node(BaseNode):
  mark = '-'
  text = 'Node'

  def __init__(self, **kwargs):
    if not kwargs.get('text') is None:
      self.text = str(kwargs.get('text'))
    self.call = kwargs.get('call')
    self._docall()

  def _docall(self):
    if self.call:
      try:
        self.text = self.call()
      except Exception as e:
        self.text = 'callerr: ' + str(e)

  def into(self):
    self._docall()



class Timer(BaseNode):
  mark = '-'

  def __init__(self, **kwargs):
    self._lastcol = 0

  @property
  def text(self):
    return strftime(TIME_FORMAT)

  def _choosefmt(self, cols):
    self._lastcol = cols
    self._timefmt = \
      "%Y-%m-%d %H:%M:%S %Z" if cols >= 23 else \
      "%Y-%m-%d %H:%M:%S" if cols >= 19 else \
      "%Y%m%d %H%M%S"

  def texttrunc(self, cols):
    if self._lastcol != cols:
      self._choosefmt(cols)
    return strftime(self._timefmt)[-cols:]




class Folder(Node):
  mark = '>'

  def __init__(self, items=[], wrap=False, **kwargs):
    super(Folder, self).__init__(**kwargs)
    self.wrap = wrap
    self.setItems(items)

  def setItems(self, items):
    self.items = items
    for item in self.items:
      item.parent = self



class Playlists(Folder):
  def __init__(self, radio, wrap=True, **kwargs):
    self.radio = radio
    super(Playlists, self).__init__(text='Playlists', wrap=wrap, **kwargs)

  def into(self):
    if DEBUG: print "into", repr(self)
    self.setItems([
      Playlist(playlist, self.radio) for playlist in sorted(self.radio.mpccommand('lsplaylists'))
    ])



class FinishException(Exception):
  pass



ticks = 0
class App(BaseNode):
  '''
  Base class of applications and applets
  '''
  ROWS = 2
  COLS = 16

  def __init__(self, lcd, folder, **kwargs):
    self.lcd = lcd
    self.folder = folder
    self.top = 0
    self.selected = 0
    self.lastmsg = None
    self.buttonfuncs = {
      LCD.LEFT: self.left,
      LCD.UP: self.up,
      LCD.DOWN: self.down,
      LCD.RIGHT: self.right,
      LCD.SELECT: self.select
    }
    self.press_at = self.ticks
    self.idle_secs = 10*IDLE_SECS
    self.lcd.set_backlight(1)
    self.backlight = True


  def left(self):
    return

  def right(self):
    return

  def up(self):
    return

  def down(self):
    return

  def select(self):
    return


  def msg2line(self, msg):
    'Truncate and pad msg to length'
    return (msg + ' '*self.COLS)[:self.COLS]


  def debugmsg(self, msg):
    print '  +%s+ %4d'%('-'*self.COLS, self.top)
    for n,m in enumerate(msg):
      print('%2d|%s|' % (n,m))
    print '  +%s+ %4d'%('-'*self.COLS, self.selected)


  def invalidatedisplay(self):
    self.lastmsg = None

  def msglist(self):
    msg = []
    cols = self.COLS-1
    for rown in range(self.ROWS):
      row = (self.top + rown) % len(self.folder.items)
      mark = self.folder.items[row].mark if row == self.selected else ' '
      msg.append(self.msg2line(mark + self.folder.items[row].texttrunc(cols)))
    return msg

  def display(self):
    msg = self.msglist()
    if msg != self.lastmsg:
      self.lastmsg = msg
      if DEBUG:
        self.debugmsg(self.lastmsg)
      self.lcd.home()
      self.lcd.message('\n'.join(self.lastmsg))


  def command(self, cmd):
    if DEBUG > 2: print DEBUG,cmd
    try:
      result = subprocess.check_output(cmd, stderr=subprocess.STDOUT).strip()
    except subprocess.CalledProcessError as e:
      if DEBUG > 4: print "---\n%s" % dir(e)
      print "Error: %s\nOutput: %s" % (str(e), e.output)
      result = ''
    result = [r.strip() for r in result.split('\n')]
    if DEBUG > 3: print cmd, '-->', result
    return result

  def mpccommand(self, incmd):
    cmd = ['mpc']
    if isinstance(incmd, str):
      cmd.append(incmd)
    else:
      cmd.extend(incmd)
    return self.command(cmd)


  @property
  def ticks(self):
    ''' number of 1/10 seconds to have elapsed '''
    return ticks

  def tick(self):
    ''' each 1/10s 'tick' through the main run loop '''
    global ticks
    if not ticks % 10:
      self.display()
      if ticks - self.press_at > self.idle_secs:
        self.lcd.set_backlight(0)
        self.backlight = False
    ticks += 1


  def run(self):
    '''
    Basic event loop of the application
    '''
    if DEBUG: print 'start:', self.folder

    kbpoll = 0.033
    ratio10ths = int(0.1/kbpoll)
    uticks = 0
    last_buttons = None

    while True:

      if self.backlight and not uticks % ratio10ths:
        self.tick()
        uticks = 0
      uticks += 1

      buttons = self.lcd.read_buttons(self.buttonfuncs.keys())

      if last_buttons == buttons:
        sleep(kbpoll)
        continue

      last_buttons = buttons
      self.press_at = self.ticks
      if not self.backlight:
        self.lcd.set_backlight(1)
        self.backlight = True

      try:
        buttons = [self.buttonfuncs[k]() for b,k in enumerate(self.buttonfuncs.keys()) if buttons[b]]
      except FinishException:
        break

      self.display()

    if DEBUG: print 'finish:', self.folder



class Applet(App):
  ''' Base class for all Applets '''
  mark = '*'

  def __init__(self, text, app, **kwargs):
    self.text = text
    super(Applet, self).__init__(app.lcd, None, **kwargs)

  def left(self):
    '''Return from applet'''
    while True:
      buttons = self.lcd.read_buttons(self.buttonfuncs.keys())
      if not sum(buttons):
        raise FinishException
      if DEBUG > 1: print 'return holding:',buttons
      sleep(0.01)



class Playlist(Applet):
  volumes = (0, 10, 40, 60, 70, 80, 85, 90, 95, 100)

  def select(self):
    self.play = not self.play
    self.mpccommand('play' if self.play else 'stop')


  def up(self):
    try:
      pos = self.volumes.index(self.volume)
    except ValueError:
      pos = self._findvolume()
    self._setvolume(pos + 1)


  def down(self):
    try:
      pos = self.volumes.index(self.volume)
    except ValueError:
      pos = self._findvolume()
    self._setvolume(pos - 1)


  def _findvolume(self):
    return len([i for i,v in enumerate(self.volumes) if v < self.volume])


  def _setvolume(self, index):
    try:
      vol = str(self.volumes[max(min(index, len(self.volumes)-1), 0)])
    except (ValueError,TypeError,IndexError):
      vol = str(index)
    self.mpccommand(['volume', vol])


  def update(self):
    try:
      self.volume = int(self.mpccommand('volume')[0].split(':')[1][:-1])
      res = self.mpccommand(['-f', '%name%\n%title%', 'current'])
      res.extend(['']*self.ROWS)
      self.lines[0] = unidecode(res[0].split(',', 1)[0]) or '{%s}'%self.text
      self.lines[1] = unidecode(res[1]) or '{volume: %d%%}'%self.volume
    except:
      self.lines[0] = 'Update failed'
      self.lines[1] = strftime(TIME_FORMAT)[1-self.COLS:]


  def display(self):
    ticks = self.ticks
    if DEBUG > 9: print ticks - self.lastdisp
    if 3 >= ticks - self.lastdisp >= 0:
      return
    if DEBUG > 1: print ticks - self.lastdisp
    self.lastdisp = ticks

    msg = [self.msg2line(l[self.rpos[n]:]) for n,l in enumerate(self.lines)]
    if msg != self.lastmsg:
      self.lastmsg = msg
      if DEBUG:
        if DEBUG > 2:
          self.debugmsg(self.lines)
        self.debugmsg(self.lastmsg)
      self.lcd.home()
      self.lcd.message('\n'.join(self.lastmsg))

    for r in range(self.ROWS):
      if self.rdir[r] == 'L':
        if self.rpos[r] + self.COLS < len(self.lines[r]):
          self.rpos[r] += 1
        else:
          self.lastdisp = ticks + 10
          self.rdir[r] = 'R'
      elif self.rdir[r] == 'R':
        self.lastdisp = ticks + 10
        self.rdir[r] = 'L'
        self.rpos[r] = 0

    if 20 >= ticks - self.lastupd >= 0:
      return
    self.lastupd = ticks

    self.update()
    for r in range(self.ROWS):
      if self.rpos[r] + self.COLS > len(self.lines[r]):
        self.rdir[r] = 'L'
        self.rpos[r] = 0


  def tick(self):
    self.display()
    super(Playlist, self).tick()


  def run(self):
    for cmd in ('clear', ['volume', '70'], ['load', self.text], 'play'):
      self.mpccommand(cmd)
    self.play = True
    self.rpos = [0] * self.ROWS
    self.rdir = ['L'] * self.ROWS
    self.lines = [''] * self.ROWS
    self.lastdisp = 0
    self.lastupd = 0
    self.update()
    super(Playlist, self).run()



class RGB(Applet):
  mark = '*'
  text = 'RGB LED'
  lnames = ('Red', 'Green', 'Blue')
  lstates = [0,0,0]

  def __init__(self, app):
    self.app = app
    self.led = 0

  def setled(self, state):
    self.lstates[self.led] = state
    self.app.lcd.set_color(*self.lstates)

  def select(self):
    self.setled(not self.lstates[self.led])

  def up(self):
    self.setled(True)

  def down(self):
    self.setled(False)

  def right(self):
    self.led = (self.led + 1) % 3

  def msglist(self):
    return ['-'.join([self.lnames[n%3] for n in range(self.led,self.led+3)]), 'up-On, dn-Off']

  def run(self):
    super(RGB, self).__init__(self.text, self.app)
    self.app.lcd.clear()
    super(RGB, self).run()


# TODO: confirm
class Shutdown(Applet):
  def __init__(self, app, restart=False, triplet=None):
    self.app = app
    self.mark = '*'
    self.text, self._msg, self._cmd = \
      triplet if triplet else \
      ('Restart',  'Restarting...\n',    ['sudo', 'reboot']) if restart else \
      ('Shutdown', 'Shutting down...\n', ['sudo', 'poweroff'])

  def run(self):
    super(Shutdown, self).__init__(self.text, self.app)
    self.lcd.home()
    self.lcd.message(self._msg)
    #sleep(1); self.left()
    self.command(self._cmd)



class Radio(App):
  '''
  The application.
  '''

  def __init__(self, lcd=None, **kwargs):
    super(Radio, self).__init__(
      lcd or Locking_CharLCDPlate(),
      Folder(items=(
        Playlists(self),
        Folder(text='Settings', items=(
          Node(call=lambda: (self.command(['hostname', '-I']) or ['NoIP'])[0]),
          Timer(),
          Shutdown(self, triplet=('Fix WiFi', 'Fixing WiFi...\n', ('sudo', '/home/pi/bin/fixWiFi', 'logit'))),
          RGB(self),
          Shutdown(self),
          Shutdown(self, restart=True),
        )),
        #Folder(text='Other', wrap=True, items=(
        #  Node(text='blargh'),
        #  Node(text='ugh'),
        #  Node(text='urk')
        #)),
      )),
      **kwargs
    )
    self.mpccommand('clear')


  def up(self):
    self.selected -= 1
    if self.selected < 0:
      self.selected = (len(self.folder.items) - 1) if self.folder.wrap else 0
      if self.ROWS < len(self.folder.items):
        self.top = self.selected
    elif self.selected < self.top:
      self.top = self.selected


  def down(self):
    if self.folder.wrap:
      self.selected = (self.selected + 1) % len(self.folder.items)
      if self.ROWS < len(self.folder.items):
        self.top = (self.selected - self.ROWS + 1 + len(self.folder.items)) % len(self.folder.items)
    else:
      self.selected = min(self.selected + 1, len(self.folder.items) - 1)
      self.top = max(self.selected - self.ROWS + 1, 0)


  def left(self):
    if not isinstance(self.folder.parent, Folder):
      return

    # find the current in the parent
    try:
      index = self.folder.parent.items.index(self.folder)
      if DEBUG:
        print 'foundit:', self.folder.parent.items[index]
    except ValueError:
      index = 0

    self.folder = self.folder.parent
    self.selected = index
    self.top = max(self.selected - self.ROWS + 1, 0)


  def right(self):
    if isinstance(self.folder.items[self.selected], Applet):
      self.folder.items[self.selected].run()
      self.invalidatedisplay()
    elif isinstance(self.folder.items[self.selected], Folder):
      self.folder = self.folder.items[self.selected]
      self.top = self.selected = 0
      self.folder.into()
    else:
      # dummy into to update item text
      self.folder.items[self.selected].into()


  def select(self):
    if isinstance(self.folder.items[self.selected], Applet):
      self.folder.items[self.selected].run()
      self.invalidatedisplay()
    else:
      # dummy into to update item text
      self.folder.items[self.selected].into()


  def run(self):

    # catch shutdown
    def myexit(*args,**kwargs): raise SystemExit('sigterm')
    signal.signal(signal.SIGTERM, myexit)

    try:
      super(Radio, self).run()
    except (KeyboardInterrupt, SystemExit):
      pass

    # cleanup
    self.lcd.clear()
    self.lcd.message('Exited\n%s' % strftime(TIME_FORMAT)[-self.COLS:])
    self.lcd.set_backlight(0)
    self.mpccommand('clear')




if __name__ == '__main__':

  import onlyone
  import sys

  def myinit():
    if not onlyone.me():
      onlyone.running()
    # Initialize the LCD using my pins
    lcd = Locking_CharLCDPlate(backlight=LCD.LCD_PLATE_SPARE, initial_color=(0,0,0))
    # my GREEN and BLUE are swapped
    lcd._blue  = LCD.LCD_PLATE_GREEN
    lcd._green = LCD.LCD_PLATE_BLUE
    return lcd

  while 'retry' in sys.argv:
    try:
      lcd = myinit()
      break
    except IOError:
      sleep(2)
  else:
      lcd = myinit()

  Radio(lcd).run()
