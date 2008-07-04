#!/usr/bin/python
from pyinotify import WatchManager, Notifier, EventsCodes, ProcessEvent
import sys

added_flag = False

class ErikPE(ProcessEvent):
	modCount = 0
	clwCount = 0
	#def process_default(self, event):
		#"""
		#override default event processing method
		#"""
		#print "ErikPE process_default()"
		#print dir(event)
		#super(ErikPE, self).process_default(event)

	def process_IN_ACCESS(self, event):
		print "file was accessed..."
		print event.event_name
		print event.name
		print event.path

	def process_IN_IGNORED(self, event):
		global added_flag
		print "file was ignored"
		print event.event_name
		print event.name
		print event.path

	def process_IN_MODIFY(self, event):
		print "fiel was modified"
		print event.event_name
		print event.name
		print event.path
		ErikPE.modCount += 1
		print "this is the %d time this event has occured" % ErikPE.modCount

	def process_IN_CLOSE_WRITE(self, event):
		print "file was closed (writable)..."
		print event.event_name
		print event.name
		print event.path
		ErikPE.clwCount += 1
		print "this is the %d time this event has occured" % ErikPE.clwCount

if sys.argv[1:]:
	path = sys.argv[1]
else:
	print "USAGE: %s <file to watch>" % sys.argv[0]
	exit(0)

mask = EventsCodes.IN_CLOSE_WRITE | \
		EventsCodes.IN_CLOSE_NOWRITE | \
		EventsCodes.IN_ACCESS

mask =  EventsCodes.IN_CLOSE_WRITE
	#EventsCodes.IN_MODIFY \
	#| EventsCodes.IN_DELETE \
	#| EventsCodes.IN_OPEN \
	#| EventsCodes.IN_ATTRIB \
	#| EventsCodes.IN_CREATE

#mask = EventsCodes.ALL_EVENTS

while True:
	try:
		if not added_flag:
			print "re-adding watch"
			wm = WatchManager()
			notifier = Notifier(wm, ErikPE())
			wm.add_watch(path, mask)
			added_flag = True
		print "gonna process_events()"
		notifier.process_events()
		print "gonna check_events()"
		if notifier.check_events():
			print "gonna read_events()"
			notifier.read_events()
	except KeyboardInterrupt:
		print "ok, fine, I'm done!"
		notifier.stop()
		break
	except Exception, err:
		print err

