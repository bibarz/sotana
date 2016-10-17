# -*- coding: utf-8 -*-
import numpy as np
import os
import time
from sotana import read_words_and_kanji, ChartParser, jReads, tokenizedRomaji, ref_string, sep_string
from flask import Flask, session, redirect, url_for, render_template


app = Flask(__name__)
app.secret_key = 'sotana'
histories = {}
session_expiration_seconds = 24 * 3600 * 7  # sessions expire after not being used for this
os.environ['PATH'] += ':/usr/local/bin'


def update_time_decorator(f):
    def wrapper(self, *args, **kwargs):
        self.last_time_used = time.time()
        return f(self, *args, **kwargs)
    return wrapper

class History(object):
    def __init__(self):
        self.last_time_used = time.time()
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

    @update_time_decorator
    def add_to_history(self, i):
        self.last_used_time = time.time()
        self.history = self.history[:self.hist_index] + [i]
        self.hist_index += 1

    @update_time_decorator
    def hist_button_status(self):
        self.last_used_time = time.time()
        status = {
            'has_prev': self.hist_index > 1,
            'has_next': self.hist_index < len(self.history),
            'index_label': str("%i/%i" % (self.hist_index, len(self.history)))
        }
        return status

    @update_time_decorator
    def history_back(self):
        self.hist_index -= 1
        self.show_next(i=self.history[self.hist_index-1], remember=False)

    @update_time_decorator
    def history_forward(self):
        self.show_next(i=self.history[self.hist_index], remember=False)
        self.hist_index += 1
        self._update_hist_button_status()


def _cleanup_histories():
    # Delete old histories after session_expiration_seconds inactive
    t = time.time()
    for c in histories.keys():
        if t - histories[c].last_time_used > session_expiration_seconds:
            del histories[c]


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
    <a href='/start_session'> Click to start </a>
    '''

@app.route('/start_session')
def start_session():
    _cleanup_histories()
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
    return ("Session expired!")
