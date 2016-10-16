# -*- coding: utf-8 -*-
import numpy as np
import subprocess
import os
from sotana import read_words_and_kanji, ChartParser, jReads, tokenizedRomaji, ref_string, sep_string
from flask import Flask, session, redirect, url_for, render_template


app = Flask(__name__)
app.secret_key = 'sotana'
histories = {}
os.environ['PATH'] += ':/usr/local/bin'


class Card(object):
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


class App():
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
        

class History(object):
    def __init__(self):
        self.history = []
        self.hist_index = 0
        self.current_kanji = None
        self.kataDict = ChartParser('data/katakanaChart.txt').chartParse()
        self.dicts, self.kanji_data = read_words_and_kanji('japdic.xlsx')
        self.default_dict_name='mimi'
        self.probs = np.ones(len(self.dicts[self.default_dict_name])) / len(self.dicts[self.default_dict_name])
        self.words = {k: [d['word'] for d in self.dicts[k]] for k in self.dicts.keys()}
        self.kanji = [d['kanji'] for d in self.kanji_data]

    def random_sample(self):
        i = np.digitize(np.random.random(1), np.cumsum(self.probs))[0]
        self.probs[i] *= 0.2
        self.probs /= np.sum(self.probs)
        return i

    def add_to_history(self, i):
        self.history = self.history[:self.hist_index] + [i]
        self.hist_index += 1

    def hist_button_status(self):
        status = {
            'has_prev': self.hist_index > 1,
            'has_next': self.hist_index < len(self.history),
            'index_label': str("%i/%i" % (self.hist_index, len(self.history)))
        }
        return status

    def history_back(self):
        self.hist_index -= 1
        self.show_next(i=self.history[self.hist_index-1], remember=False)

    def history_forward(self):
        self.show_next(i=self.history[self.hist_index], remember=False)
        self.hist_index += 1
        self._update_hist_button_status()


def _get_session_history():
    if 'code' not in session:
        return False, redirect(url_for('no_session'))
    code = session['code']
    if code not in histories:
        return False, redirect(url_for('no_session'))
    return True, histories[code]


@app.route('/')
def default():
    return '''
    <a href='/start_session'> Start! </a>
    '''

@app.route('/start_session')
def start_session():
    code = np.random.random()
    session['code'] = code
    histories[code] = History()
    return redirect(url_for('new_card'))


def _make_kanji_rule(h, c):
    return  url_for('new_card', index=h.history[h.hist_index - 1][0],
                    dict_name=h.history[h.hist_index - 1][1],
                    remember=False, kanji=c, show_all=True)


def _make_kanji_list(h, kanjis):
    kanji_list = []
    for c in kanjis:
        is_linkable = (0x4e00 <= ord(c) <= 0x9faf) and (c in h.kanji)  # it is a kanji and we have it in the database
        kanji_list.append(dict(value=c, has_link=is_linkable, link=(_make_kanji_rule(h, h.kanji.index(c)) if is_linkable else None)))
    return kanji_list


@app.route('/new_card')
@app.route('/new_card/<int:index>')
@app.route('/new_card/<int:index>/<dict_name>')
@app.route('/new_card/<int:index>/<dict_name>/<int:remember>')
@app.route('/new_card/<int:index>/<dict_name>/<int:remember>/<int:kanji>')
@app.route('/new_card/<int:index>/<dict_name>/<int:remember>/<int:kanji>/<int:show_all>')
def new_card(index=None, dict_name=None, remember=True, kanji=None, show_all=False):
    success, h = _get_session_history()
    if not success:
        return h

    if dict_name is None:
        dict_name = h.default_dict_name

    if kanji is not None:
        h.current_kanji = kanji

    while index is None:
        index = h.random_sample()
        if h.dicts[h.default_dict_name][index]['lesson'] > 150000:
            index = None

    if remember:
        h.add_to_history((index, dict_name))

    data = h.dicts[dict_name][index]

    kana = ''.join([x.split(',')[-1] for x in jReads(data['word'])])
    romaji = ' '.join(tokenizedRomaji(unicode(data['word']))).encode('utf-8')
    ref = ref_string(data)
    related = []
    if data['related words']:
        words = sep_string(data['related words'])
        for i, w in enumerate(words):
            w = w.strip()
            for k in h.words.keys():
                if w in h.words[k]:
                    related.append(dict(value=w, has_link=True,
                                        link=url_for('new_card', index=h.words[k].index(w),
                                                     dict_name=k, remember=True)))
                    break
            else:
                related.append(dict(value=w, has_link=False, link=None))


    word = _make_kanji_list(h, data['word'])

    example = ''
    if 'example' in data and data['example']:
        example = data['example']

    main_dict = dict(meaning=data['meaning'],
                     kana=kana, romaji=romaji,
                     ref=ref_string(data),
                     related=related,
                     word=word,
                     example=example,
                     show_all=show_all)

    if h.current_kanji is None:
        kanjidict = {}
    else:
        kanji_data = h.kanji_data[h.current_kanji]
        related_kanji = _make_kanji_list(h, sep_string(kanji_data['related kanji']))

        kanjidict = dict(kanji=kanji_data['kanji'],
                         kanjikun=kanji_data['kun'],
                         kanjion=kanji_data['on'],
                         kanjirelated=related_kanji,
                         kanjimeaning=kanji_data['meaning'],
                         kanjimnemo=kanji_data['explanation']
                         )

    main_dict.update(kanjidict)
    main_dict.update(h.hist_button_status())

    return render_template('card.html', **main_dict)


@app.route('/prev_card')
def prev_card():
    success, h = _get_session_history()
    if not success:
        return h
    h.hist_index -= 1
    return redirect(url_for('new_card', index=h.history[h.hist_index - 1][0],
                            dict_name=h.history[h.hist_index - 1][1], remember=False,
                            kanji=h.current_kanji))


@app.route('/next_card')
def next_card():
    success, h = _get_session_history()
    if not success:
        return h
    h.hist_index += 1
    return redirect(url_for('new_card', index=h.history[h.hist_index - 1][0],
                            dict_name=h.history[h.hist_index - 1][1], remember=False,
                            kanji=h.current_kanji))


@app.route('/no_session')
def no_session():
    return ("No session!")
