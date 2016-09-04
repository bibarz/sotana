# -*- coding: utf-8 -*-
import Tkinter as Tk
import tkFont
import sys
import numpy as np
import webbrowser
import urllib
import xlrd
import xml.etree.cElementTree as etree
import re
import subprocess
import StringIO


def cabocha_xml(sent):
    """
    @return type = unicode
    -xml format unicode string is returned 
    """
    command = 'cabocha -f 3'
    p = subprocess.Popen(command, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    output, _ = p.communicate(sent)
    return unicode(output, 'utf8')


class ChartParser(object):
    def __init__(self, chartFile):
        with open('katakanaChart.txt') as f:
            self.chart = f.readlines()

    def chartParse(self):
        """
        @return chartDict
        ガ ==> g,a
        キ ==> k,i
        キャ ==> k,ya
        Similarily for Hiragana
        @setrofim : http://www.python-forum.org/pythonforum/viewtopic.php?f=3&t=31935
        """
        lines = self.chart
        chartDict = {}
        output = {}
        col_headings = lines.pop(0).split()
        for line in lines:
            cells = line.split()
            for i, c in enumerate(cells[1:]):
                output[c] = (cells[0], col_headings[i])
        for k in sorted(output.keys()):
            #@k = katakana
            #@r = first romaji in row
            #@c = concatinating romaji in column
            r, c = output[k]
            k, r, c = [unicode(item,'utf-8') for item in [k,r,c]]
            if k == 'X':continue
            if r=='s' and c[0] == 'y':
                c = 'h' + c[1:]
            if r=='s' and c == 'i':
                c = 'hi'
            if r=='j' and c[0] == 'y':
                c = c[1:]
            if r=='t' and c[0] == 'y':
                r = 'c'
                c = 'h' + c[1:]
            romaji = ''.join([item.replace('X', '') for item in [r,c]])
            chartDict[k] = romaji
        return chartDict
    
def tokenizedRomaji(jSent):
    kataDict = ChartParser('data/katakanaChart.txt').chartParse()
    tokenizeRomaji = []
    def check_duplicate(s, duplicate):
        if not duplicate:
            return s
        else:
            return s[0] + s

    duplicate = False
    for kataChunk in jReads(jSent):
        romaji = ''
        for idx, kata in enumerate(kataChunk,1):
            if idx != len(kataChunk):
                doubles = kata+kataChunk[idx]
                if kataDict.has_key(doubles):
                    romaji += check_duplicate(kataDict[doubles], duplicate)
                    duplicate = False
                    continue
            if kataDict.has_key(kata):
                next_romaji = kataDict[kata]
                if next_romaji == 'hu':
                    next_romaji = 'fu'
                romaji += check_duplicate(kataDict[kata], duplicate)
                duplicate = False
            elif ord(kata) == 12483:  # 12483 = unicode for ッ 
                duplicate = True
            else:
                duplicate = False
                pass
                #checkPunctuation(kata)
        tokenizeRomaji.append(romaji)
    return tokenizeRomaji


def jReads(target_sent):
    sentence = etree.fromstring(cabocha_xml(target_sent.encode('utf-8')).encode('utf-8'))
    return [tok.get("feature").split(',')[-1] for chunk in sentence for tok in chunk.findall('tok')]


def sep_string(s):
    return [x for x in s.replace(unicode(u'\u3001'), ',').replace(unicode(u'\uff0c'),',').split(',') if x]    


def read_words_and_kanji(filename):
    dicts = {}
    for sheet in ['EK1', 'EK2', 'EK2Old', 'JBP3', 'mimi']:
        workbook = xlrd.open_workbook(filename)
        worksheet = workbook.sheet_by_name(sheet)
        num_cells = worksheet.ncols
        fields = ['word', 'meaning', 'kanji', 'page', 'lesson', 'related words', 'example']
        #assert num_cells >= len(fields)
        dict_words = [dict(zip(fields, v[:len(fields)])) for v in worksheet._cell_values]
        dicts[sheet] = dict_words

    worksheet = workbook.sheet_by_name('Kanji')
    num_cells = worksheet.ncols
    fields = ['kanji', 'kun', 'on', 'related kanji', 'meaning', 'explanation']
    assert num_cells >= len(fields)
    dict_kanji = [dict(zip(fields, v[:len(fields)])) for v in worksheet._cell_values]

    return dicts, dict_kanji


def to_str(x):
    if isinstance(x, (float, int)):
        return ('%i' % x)
    else:
        return x


def ref_string(data):       
    k = to_str(data['kanji'])
    p = to_str(data['page'])
    l = to_str(data['lesson'])
    return "k %s, p %s, l %s" % (k, p, l)


def browse_kanji(c):
    url = "http://www.romajidesu.com/kanji/"
    controller = webbrowser.get('firefox')
    controller.open(url + urllib.quote(c.encode('utf-8')))


class Card(object):
    kataDict = ChartParser('data/katakanaChart.txt').chartParse()
    def __init__(self, n_frames, app, frame, **params):
        self.app = app
        self.card_frame = frame
        self.frames = [Tk.Frame(frame, **params) for _ in range(n_frames)]
        self.blinders = [Tk.Frame(frame, **params) for _ in self.frames]
        for i, b in enumerate(self.blinders):
            b.bind("<Button-1>", lambda event, i=i: self.turn(i))
            
        for i, (f, b) in enumerate(zip(self.frames, self.blinders)):
            b.grid(row=i)
            f.grid(in_=b)

        self.visible = [False for _ in self.frames]

    def turn(self, i):
        if self.visible[i]:
            self.frames[i].lower(self.blinders[i])
        else:
            self.frames[i].lift(self.blinders[i])
        self.visible[i] = not self.visible[i]

    def reveal_more(self):
        for i, v in enumerate(self.visible):
            if not v:
                self.turn(i)
                return
        # All is revealed; hide last
        self.turn(-1)


class WordCard(Card):
    def __init__(self, data, *args, **kwargs):
        Card.__init__(self, 3, *args, **kwargs)

        format = {'fg': 'white',
                  'bg': 'black'}

        l = Tk.Label(self.frames[0], text=data['meaning'], font=("Lucida Grande", 20), **format)
        l.bind("<Button-1>", lambda event: self.turn(0))
        l.grid(row=0)
        
        kana = ''.join([x.split(',')[-1] for x in jReads(data['word'])])
        romaji = ' '.join(tokenizedRomaji(unicode(data['word']))).encode('utf-8')
        for col, c in enumerate(data['word']):
            l = Tk.Label(self.frames[2], text=c, font=("Lucida Grande", 60), **format)
            if 0x4e00 <= ord(c) <= 0x9faf:  # kanji
                l.bind("<Button-1>", lambda event, c=c: self.app.show_kanji(c))
            else:
                l.bind("<Button-1>", lambda event: self.turn(2))
            l.grid(row=0, column=col)

        l = Tk.Label(self.frames[1], text=kana, font=("Lucida Grande", 20), **format)
        l.bind("<Button-1>", lambda event: self.turn(1))
        l.grid(row=0)
        l = Tk.Label(self.frames[1], text=romaji, font=("Lucida Grande", 20), **format)
        l.bind("<Button-1>", lambda event: self.turn(1))
        l.grid(row=1)
        l = Tk.Label(self.frames[1], text=ref_string(data), font=("Lucida Grande", 20), **format)
        l.bind("<Button-1>", lambda event: self.turn(1))
        l.grid(row=2)

        if data['related words']:
            related_frame = Tk.Frame(self.frames[1], bg='black')
            words = sep_string(data['related words'])
            for i, w in enumerate(words):
                w = w.strip()
                for k in self.app.words.keys():
                    if w in self.app.words[k]:
                        elem = Tk.Button(related_frame, text=w, font=("Lucida", 20),
                                         command=lambda i=(self.app.words[k].index(w), k): self.app.show_next(i),
                                         **format)
                        break
                else:
                    elem = Tk.Label(related_frame, text=w, font=("Lucida", 20), **format)
                elem.grid(row=0, column=i)
            related_frame.grid(row=3)

        if 'example' in data and data['example']:
            example_frame = Tk.Frame(self.frames[2], bg='black')
            l = Tk.Text(example_frame, font=("Lucida Grande", 14), width=30,
                        height=len(data['example'])/30 + 1, **format)
            l.insert('1.0', data['example'])
            l.grid(row=0)
            example_frame.grid(row=1, columnspan=len(data['word']))


class KanjiCard(Card):
    def __init__(self, data, *args, **kwargs):
        Card.__init__(self, 6, *args, **kwargs)

        format = {'fg': 'white',
                  'bg': 'black'}

        l = Tk.Label(self.frames[0], text=data['kanji'], font=("Lucida Grande", 60), **format)
        l.bind("<Button-1>", lambda event: browse_kanji(data['kanji']))
        l.grid(row=0)
        
        for col, c in enumerate(sep_string(data['kun'])):
            l = Tk.Label(self.frames[1], text=c, font=("Lucida Grande", 20), **format)
            l.bind("<Button-1>", lambda event, c=c: self.app.kanjis_with_kun(c))
            l.grid(row=0, column=col)
        for col, c in enumerate(sep_string(data['on'])):
            l = Tk.Label(self.frames[2], text=c, font=("Lucida Grande", 20), **format)
            l.bind("<Button-1>", lambda event, c=c: self.app.kanjis_with_on(c))
            l.grid(row=0, column=col)
        for col, c in enumerate(sep_string(data['related kanji'])):
            l = Tk.Label(self.frames[3], text=c, font=("Lucida Grande", 40), **format)
            if 0x4e00 <= ord(c) <= 0x9faf:  # kanji
                l.bind("<Button-1>", lambda event, c=c: self.app.show_kanji(c))
            l.grid(row=0, column=col)

        l = Tk.Text(self.frames[4], font=("Lucida Grande", 28), width=len(data['meaning']), height=1, **format)
        l.insert('1.0', data['meaning'])
        l.bind("<Button-1>", lambda event, c=c: self.app.words_from_kanji(data['kanji']))
        l.grid(row=0)
        l = Tk.Text(self.frames[5], font=("Lucida Grande", 14), width=30, height=len(data['explanation']) / 30 + 1, **format)
        l.insert('1.0', data['explanation'])
        l.grid(row=0)

        for i in range(1, 6):
            self.turn(i)


class App(Tk.Frame):
    def __init__(self, dict_data, kanji_data, default_dict_name, master=None, **params):
        Tk.Frame.__init__(self, master, **params)
        self.grid(sticky=Tk.N + Tk.S + Tk.E + Tk.W)  # make it resizable
        self.dict_data = dict_data
        self.default_dict_name = default_dict_name
        self.kanji_data = kanji_data
        self.words = {k: [d['word'] for d in dict_data[k]] for k in dict_data.keys()}
        self.kanji = [d['kanji'] for d in kanji_data]
        self.history = []
        self.hist_index = 0
        self.probs = np.ones(len(self.dict_data[self.default_dict_name])) / len(self.dict_data[self.default_dict_name])
        
        btn = Tk.Button(self, text='New', command=self.show_next)
        btn.grid(row=0, column=0)
        self.prev_btn = Tk.Button(self, text='Prev', command=self.history_back)
        self.prev_btn.grid(row=0, column=1)
        self.next_btn = Tk.Button(self, text='Next', command=self.history_forward)
        self.next_btn.grid(row=0, column=2)
        self.idx_label = Tk.Label(self, text='', font=("Lucida Grande", 14), fg='white', bg='black')
        self.idx_label.grid(row=0, column=3)
        self.card_frame = Tk.Frame(self, **params)
        self.card_frame.grid(row=1, columnspan=4)
        self.kanji_frame = None
        self.kanji_list_frame = None
        self.word_list_frame = None
        self.bind_all("<Right>", self.next_or_forward)
        self.bind_all("<Left>", self.nothing_or_backward)
        self.bind_all("<space>", self.reveal_more)
        
        self.show_next()
        self.grid()
        
    def reveal_more(self, event):
        self.last_word_card.reveal_more()

    def next_or_forward(self, event):
        if self.next_btn['state'] == 'disabled':
            self.show_next()
        else:
            self.history_forward()

    def nothing_or_backward(self, event):
        if self.prev_btn['state'] == 'disabled':
            return
        else:
            self.history_back()

    def add_to_history(self, i):
        self.history = self.history[:self.hist_index] + [i]
        self.hist_index += 1
        self._update_hist_button_status()

    def history_back(self):
        self.hist_index -= 1
        self.show_next(i=self.history[self.hist_index-1], remember=False)
        self._update_hist_button_status()

    def history_forward(self):
        self.show_next(i=self.history[self.hist_index], remember=False)
        self.hist_index += 1
        self._update_hist_button_status()

    def _update_hist_button_status(self):
        self.prev_btn['state'] = 'disabled' if self.hist_index == 1 else 'normal'
        self.next_btn['state'] = 'disabled' if self.hist_index >= len(self.history) else 'normal'
        self.idx_label['text'] = str("%i/%i" % (self.hist_index, len(self.history)))

    def random_sample(self):
        i = np.digitize(np.random.random(1), np.cumsum(self.probs))[0]
        self.probs[i] *= 0.2
        self.probs /= np.sum(self.probs)
        return i

    def show_next(self, i=None, remember=True):
        # i can be:
        #     None, meaning take a random card from default deck
        #     an integer: index in default deck
        #     a tuple (index, dict_name)
        while i is None:
            i = self.random_sample()
            if self.dict_data[self.default_dict_name][i]['lesson'] > 150000:
                i = None
        if remember:
            self.add_to_history(i)
        for w in self.card_frame.winfo_children():
            if isinstance(w, Tk.Frame):
                w.destroy()
        idx, key = (i, self.default_dict_name) if isinstance(i, (float, int)) else i
        self.last_word_card = WordCard(self.dict_data[key][idx], self, self.card_frame, bg='black')
        self.last_word_card.turn(0)

    def show_kanji(self, c):
        if c not in self.kanji:
            browse_kanji(c)
            return

        i = self.kanji.index(c)

        if self.kanji_frame is None:
            self.kanji_frame = Tk.Toplevel(self, bg='black')
            self.kanji_frame.geometry('+400+0')
            self.kanji_frame.protocol("WM_DELETE_WINDOW", self.kanji_frame_closed)

        for w in self.kanji_frame.winfo_children():
            if isinstance(w, Tk.Frame):
                w.destroy()

        self.last_kanji_card = KanjiCard(self.kanji_data[i], self, self.kanji_frame, bg='black')
        self.last_kanji_card.turn(0)
    
    def kanji_frame_closed(self):
        self.kanji_frame.destroy()
        self.kanji_frame = None

    def show_kanji_list(self, kanji_list, **format):
        if self.kanji_list_frame is None:
            self.kanji_list_frame = Tk.Toplevel(self, bg='black')
            self.kanji_list_frame.geometry('+100+400')
            self.kanji_list_frame.protocol("WM_DELETE_WINDOW", self.kanji_list_frame_closed)

        for w in self.kanji_list_frame.winfo_children():
            if isinstance(w, Tk.Widget):
                w.destroy()

        format = {'fg': 'white',
                  'bg': 'black'}

        for i, c in enumerate(kanji_list):
            l = Tk.Label(self.kanji_list_frame, text=c, font=("Lucida Grande", 60), **format)
            l.bind("<Button-1>", lambda event, c=c: self.show_kanji(c))
            l.grid(row=0, column=i)

    def kanji_list_frame_closed(self):
        self.kanji_list_frame.destroy()
        self.kanji_list_frame = None

    def kanjis_with_kun(self, c):
        k_list = []
        for d in self.kanji_data:
            kuns = sep_string(d['kun'])
            if c in kuns:
                k_list.append(d['kanji'])
        self.show_kanji_list(k_list)
        
    def kanjis_with_on(self, c):
        k_list = []
        for d in self.kanji_data:
            ons = sep_string(d['on'])
            if c in ons:
                k_list.append(d['kanji'])
        self.show_kanji_list(k_list)

    def show_word_list(self, word_index_list, **format):
        if self.word_list_frame is None:
            self.word_list_frame = Tk.Toplevel(self, bg='black')
            self.word_list_frame.geometry('+100+400')
            self.word_list_frame.protocol("WM_DELETE_WINDOW", self.word_list_frame_closed)

        for w in self.word_list_frame.winfo_children():
            if isinstance(w, Tk.Widget):
                w.destroy()

        format = {'fg': 'white',
                  'bg': 'black'}

        for i, index in enumerate(word_index_list):
            idx, key = (index, self.default_dict_name) if isinstance(index, (float, int)) else index
            l = Tk.Label(self.word_list_frame, text=self.dict_data[key][idx]['word'], font=("Lucida Grande", 40), **format)
            l.bind("<Button-1>", lambda event, index=index: self.show_next(index))
            l.grid(row=0, column=i)

    def word_list_frame_closed(self):
        self.word_list_frame.destroy()
        self.word_list_frame = None

    def words_from_kanji(self, c):
        word_index_list = []
        for key in self.dict_data.keys():
            for i, d in enumerate(self.dict_data[key]):
                if c in d['word']:
                    word_index_list.append((i, key))
        self.show_word_list(word_index_list)
        


if __name__=='__main__':
#    url = "http://docs.python.org/library/webbrowser.html"
#    webbrowser.open(url,new=2)
    import os
    os.environ['PATH'] += ':/usr/local/bin'
    dicts, kanji = read_words_and_kanji('japdic.xlsx')
    a = App(dicts, kanji, default_dict_name='mimi', bg="black")
    a.master.title('Kanji')
    a.mainloop()
