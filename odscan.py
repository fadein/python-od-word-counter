#!/usr/bin/python

import logging
import operator
import os
import sys
import xml.dom.minidom
import zipfile
from pyinotify import WatchManager, ThreadedNotifier, EventsCodes, ProcessEvent

import pygtk
pygtk.require('2.0')
import gtk;
import gtk.glade;

#TODO list:
#1.  Put treeviews into their own class to clean up __init__()
#2.  Don't split words on whitespace; find a better way to do it that won't
#       choke on apostraphes
#4.  Refactor OdtAnalyzer class to make it easier for it to do all of its tests
#       in one location; I don't want to make many passes over the text right now.
#       I don't mind making many passes over each para, though.
#5.  Fix Inotify support; the threaded listner doesn't work.  Made a test file
#    called pythino.py; use that to figure this out.  pyinotest.py works pretty
#    well...


gladefile = 'odscan.glade'
logging.basicConfig(level=logging.DEBUG,
        datefmt='%H:%M:%S',
        format='%(asctime)s %(levelname)s %(message)s',)

class WordCountTree:
    """instantiates the treeview containing the wordcount"""
    def __init__(self, treeView):
        self.treeView = treeView
        self.cWord, self.sWord = 0,'Word'
        self.cCount, self.sCount = 1, 'Count'

        #Fill in the tvAnalysis with columns
        colm = gtk.TreeViewColumn(self.sWord, gtk.CellRendererText(), text=self.cWord)
        colm.set_resizable(True)
        colm.set_sort_column_id(self.cWord)
        treeView.append_column(colm)
        treeView.set_expander_column(colm)

        colm = gtk.TreeViewColumn(self.sCount, gtk.CellRendererText(), text=self.cCount)
        colm.set_resizable(True)
        colm.set_sort_column_id(self.cCount)
        treeView.append_column(colm)

class IgnoreWordsTree:
    """instantiates the treeview containing the list of words to exclude from analysis"""
    cWord, sWord = 0,'Ignored Word'
    def __init__(self, treeView):
        self.treeView = treeView

        #Fill in the tvAnalysis with columns
        colm = gtk.TreeViewColumn(IgnoreWordsTree.sWord,
                gtk.CellRendererText(),
                text=IgnoreWordsTree.cWord)
        colm.set_resizable(True)
        colm.set_sort_column_id(IgnoreWordsTree.cWord)
        treeView.append_column(colm)
        treeView.set_expander_column(colm)

class ODScanGUI:
    def __init__(self, file):
        self.filename = file #name of file to analyze
        self.notifier = None #pyinotify

        self.wTree = gtk.glade.XML(gladefile, "toplevel")
        self.toplevel = self.wTree.get_widget('toplevel')
        self.toplevel.connect('delete_event', self.OnDeleteEvent)
        d = {   "on_open1_activate" : self.OnOpen,
                "on_btRefresh_clicked" : self.OnRefresh,
                "on_quit1_activate" : self.OnQuit,
                "on_btIgnoreAdd_clicked" : self.OnIgnoreAdd,
                "on_btIgnoreRemove_clicked" : self.OnIgnoreRemove,
            }
        self.wTree.signal_autoconnect(d)

        #instantiate a WordCountTree, but return the gtk.TreeView it contains
        self.tvAnalysis = WordCountTree(self.wTree.get_widget("tvAnalysis")).treeView
        #create a treestore model to use with tvAnalysis
        self.tsAnalysis = gtk.ListStore(str, str)
        #attach model to tvAnalysis
        self.tvAnalysis.set_model(self.tsAnalysis)
        #set selection mode
        self.tvAnalysis.get_selection().set_mode(gtk.SELECTION_BROWSE)

        #instantiates an IngoreWordsTree, but return the gtk.TreeView it contains
        self.tvIgnore = IgnoreWordsTree(self.wTree.get_widget("tvIgnore")).treeView
        #create a treestore model to use with tvIgnore
        self.tsIgnore = gtk.ListStore(str, str)
        #attach model to tvAnalysis
        self.tvIgnore.set_model(self.tsIgnore)
        #set selection mode
        #self.tvIgnore.get_selection().set_mode(gtk.SELECTION_BROWSE)
        #read in ignored words
        self.ignoreWords = IgnoreWords()
        #populate it
        for item in self.ignoreWords.words:
            try:
                self.tsIgnore.append([item, IgnoreWordsTree.cWord])
            except ValueError:
                pass

        #if filename was passed on cmdline, open it
        logging.info(self.filename)
        if self.filename != None:
            logging.info("gonna open file " + self.filename)
            self.InitInotify()
            self.OpenFile()

    def OnDeleteEvent(self, widget, event):
        """TODO: fix this!"""
        if self.notifier != None:
            print "need to stop a notifier"
            self.notifier.stop()
        return True

    def OnQuit(self, widget):
        if self.notifier != None:
            print "need to stop a notifier"
            self.notifier.stop()
        gtk.main_quit()

    def InitInotify(self):
        """initialize the inotify interface"""
        logging.info('initializing an inotify listner')
        wm = WatchManager()
        iep = InoEventProc(self)
        self.notifier = ThreadedNotifier(wm, iep)
        self.notifier.start()
        wm.add_watch(self.filename, EventsCodes.ALL_EVENTS)

    def OnIgnoreRemove(self, widget):
        """Remove word from ignore list and corresponding textfile"""
        logging.warn(" OnIgnoreRemove")
        (modl, iter) = self.tvIgnore.get_selection().get_selected()       
        if None != iter:
            self.ignoreWords.removeWord(modl.get_value(iter, IgnoreWordsTree.cWord))
            self.tsIgnore.remove(iter)
            self.Rescan()
    
    def OnIgnoreAdd(self, widget):
        """Add word to ignore list and corresponding textfile"""
        logging.warn(" OnIgnoreAdd")
        wTree = gtk.glade.XML(gladefile, "dlgNewWord")
        dlg = wTree.get_widget("dlgNewWord")
        result = dlg.run()
        if (result == gtk.RESPONSE_OK):
            entry = wTree.get_widget("entAddWord")
            newWord = entry.get_text().strip().lower()
            if newWord != '':
                self.ignoreWords.addWord(newWord)
                self.tsIgnore.append([newWord, 1])
                self.Rescan()

        dlg.destroy()

    def OnOpen(self, widget):
        """Displays file selection dialog - allows user to choose a document"""
        openDlg = FileChooser()
        result, filename = openDlg.run()
        if (result == gtk.RESPONSE_OK):
            self.filename = filename
            self.OpenFile()

    def OpenFile(self):
        """Performs the work of loading the ODF document"""
        self.tsAnalysis.clear()
        self.Scan()

    def OnRefresh(self, widget):
        """called when refresh button is clicked"""
        self.Rescan()

    def Rescan(self):
        """Clear out the word freq. treeview & reload it"""
        self.tsAnalysis.clear()
        self.Scan()

    def Scan(self):
        """creates an OdtAnalyzer object which analyzes the document"""
        if zipfile.is_zipfile(self.filename):
            myodf = OdtAnalyzer(self.filename, IgnoreWords())
            lblWordcount = self.wTree.get_widget("lblWordCount")
            lblWordcount.set_label(str(myodf.wordCount))
            lblParagraphCount = self.wTree.get_widget("lblParagraphCount")
            lblParagraphCount.set_label(str(myodf.paragraphCount))
            self.PopulateTree(myodf)

    def PopulateTree(self, odfreader):
        for item in odfreader.totalList:
            self.tsAnalysis.append(item)

class OdtAnalyzer:
    def __init__(self, filename, ignoreWords=None):
        """
        Open an ODF file, initialize list of 'Bad Words (TM)'
        """
        self.filename = filename
        self.m_odf = zipfile.ZipFile(filename)
        self.filelist = self.m_odf.infolist()
        self.text_in_paras = []
        self.wordCounter = {}
        self.badWords = ignoreWords
        self.totalList = []
        self.paragraphCount = 0
        self.wordCount = 0

        #perform the scan
        self.DoScan()

    def DoScan(self):
        self.GetContents()
        self.CountWords()

    def ShowManifest(self):
        """ show which files exist in the ODF document """
        for s in self.filelist:
            #print s.orig_filename, s.date_time, s.filename, s.file_size, s.compress_size
            print s.orig_filename

    def GetContents(self):
        """ read the paragraphs from the content.xml file """
        ostr = self.m_odf.read('content.xml')
        doc = xml.dom.minidom.parseString(ostr)
        paras = doc.getElementsByTagName('text:p')
        self.paragraphCount = len(paras)
        #print "There are" , len(paras) , "paragraphs in", sys.argv[1]
        #self.text_in_paras = []
        for p in paras:
            for ch in p.childNodes:
                if ch.nodeType == ch.TEXT_NODE:
                    self.text_in_paras.append(ch.data)

    def FindIt(self, name):
        for s in self.text_in_paras:
            if name in s:
                print s.encode('utf-8')

    def DumpText(self):
        for s in self.text_in_paras:
            print "<", s, ">"

    def CountWords(self):
        for para in self.text_in_paras:
            #logging.info(para)
            for word in para.split():
                word = word.encode('utf-8').strip(r' -;,".!?()' + "'").lower()
                self.wordCount += 1
                if self.wordCounter.has_key(word):
                    self.wordCounter[word] += 1
                else:
                    self.wordCounter[word] = 1
        #remove words from the ignore list
        #                            function                            iterable
        self.totalList = sorted( map(lambda x: [x, self.wordCounter[x]], self.PareDown()),
                key=operator.itemgetter(1), reverse=True)

    def PareDown(self):
        """copies self.wordCounter and removes items from it"""
        retval = self.wordCounter.copy()
        if self.badWords != None:
            for badWord in self.badWords.words:
                if retval.has_key(badWord):
                    del retval[badWord]
        return retval
    
class FileChooser:
    """Open File dialog"""
    def __init__(self, winTitle="Choose a file", dirs=[], defaultFile=''):
        self.winTitle = winTitle
        self.dirs = dirs
        self.defaultFile = defaultFile

    def OnKeypress(self, widget, event):
        if gtk.gdk.keyval_name(event.keyval) == 'Return':
            self.okButton.clicked()

    def run(self):
        """this function will show the FileChooser dialog"""
    
        #load the dialog from the glade
        self.wTree = gtk.glade.XML(gladefile, "filechooserdialog") 

        #get the actual dialog object
        self.dlg = self.wTree.get_widget("filechooserdialog")
        self.dlg.set_title(self.winTitle)
        if self.defaultFile != '':
            self.dlg.set_filename(self.defaultFile)
        self.dlg.set_do_overwrite_confirmation(True)
        self.dlg.connect('key_press_event', self.OnKeypress)
        self.okButton = self.wTree.get_widget('filechooserOK')

        if len(self.dirs) == 0:
            self.dlg.set_current_folder(os.getcwd())
        else:
            self.dlg.set_current_folder(self.dirs[0])
            for f in self.dirs:
                self.dlg.add_shortcut_folder(f)

        #run the dialog and store the response
        self.result = self.dlg.run()
        file = self.dlg.get_filename()

        #done with the dialog, destroy
        self.dlg.destroy()

        return self.result, file

class IgnoreWords:
    """list of words to ignore in analysis"""

    def __init__(self):
        self.words = []
        self.ignoreFile = './IgnoreWords.txt'

        try:
            b = open(self.ignoreFile, 'r')
            for line in b:
                self.words.append(line.strip().lower())
            b.close()
        except IOError, (errno, strerror):
            #a default list of words to ignore
            self.words = [ 'a', 'the', 'to', 'her', 'she',
                    'and', 'they', 'with', 'but', 'is', 'he',
                    'of', 'at', 'that', 'this', 'was']
            #write out this limited list if the file is not present.
            self.writeFile()
        except:
            print "Unknown error:", sys.exc_info()[0]
        else:
            b.close()

    def writeFile(self):
        try:
            b = open(self.ignoreFile, 'w')
            for word in self.words:
                word += "\n"
                b.write(word)
        except IOError, (errno, strerror):
            pass

    def removeWord(self, word):
        try:
            self.words.remove(word.strip().lower()) 
        except ValueError:
            print "Failed to remove %s from Ignored words list" % word
        else:
            self.writeFile()

    def addWord(self, word):
        if not self.words.__contains__(word):
            self.words.append(word)
            self.writeFile()

class InoEventProc(ProcessEvent):
    def __init__(self, tree):
        self.tree = tree

	def process_IN_CLOSE_WRITE(self, event):
		print "file %s did a %s" % (event.event_name, event.path)
        self.tree.Rescan()

if __name__ == '__main__':
    """
    pass in the name of the incoming file and the
    phrase as command line arguments.  Use sys.argv[]
    """
    file = None
    if len(sys.argv) > 1:
        file = sys.argv[1]

    odsg = ODScanGUI(file)

    gtk.main()

# vim:set ft=python ff=unix expandtab ts=4 sw=4:
