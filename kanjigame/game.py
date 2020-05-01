import operator
import os
import pickle
import random
import re
import sys
import time
from collections import OrderedDict, defaultdict
from itertools import chain
from typing import List, Optional

import pygame
import romkan
from jamdict import Jamdict

JMD = Jamdict()

if not os.path.exists('data'):
    os.mkdir('data')

WORDS_FREQ_FILEPATH = "data/nf_words_freq"


def generate_word_frequency_file(filepath):
    nf_to_kanjis = defaultdict(set)
    for entry in JMD.jmdict_xml.entries:
        for word in chain(entry.kanji_forms, entry.kana_forms):
            for pri in word.pri:
                if pri.startswith('nf'):
                    nf_x = int(pri[-2:])
                    nf_to_kanjis[nf_x].add(word.text)

    with open(filepath, "w") as outfile:
        for nf_x in sorted(nf_to_kanjis.keys()):
            for word in nf_to_kanjis[nf_x]:
                print(word, file=outfile)


def gen_word_to_freqrank():
    _word_to_freqrank = {}
    if not os.path.exists(WORDS_FREQ_FILEPATH):
        generate_word_frequency_file(WORDS_FREQ_FILEPATH)
    with open(WORDS_FREQ_FILEPATH) as infile:
        for idx, line in enumerate(infile):
            word = line.rstrip()
            _word_to_freqrank[word] = idx
    return _word_to_freqrank


WORD_TO_FREQRANK = gen_word_to_freqrank()


def word_to_freqrank(word):
    return WORD_TO_FREQRANK.get(word, sys.maxsize)


BLUE = (40, 120, 230)
GREEN = (40, 230, 120)
RED = (230, 40, 40)
ORANGE = (230, 120, 40)
WHITE = (255, 255, 255)
YELLOW = (255, 255, 0)
GRAY = (128, 128, 128)

# 1-6 for primary school, 8 for secondary school
KANJI_GRADE_TO_INFO = {
    1: {"desc": "教育第１学年", "score": 1},
    2: {"desc": "教育第２学年", "score": 2},
    3: {"desc": "教育第３学年", "score": 3},
    4: {"desc": "教育第４学年", "score": 4},
    5: {"desc": "教育第５学年", "score": 5},
    6: {"desc": "教育第６学年", "score": 6},
    8: {"desc": "常用", "score": 7},
}
KANJI_GRADES = sorted(KANJI_GRADE_TO_INFO.keys())
MAX_KANJI_GRADE = KANJI_GRADES[-1]

# Game config
JOKER_WORD_POOL_SIZE = 3  # Number of words to consider when picking a random word as a joker
MATCH_LAST_KANJI = False  # If True, only accept words starting with last kanji of previous word
ALWAYS_CLEAR_KANJI = False  # If True, even if the player fails to find a word for a kanji,
                            # it is cleared from the candidates list
WORDS_MIN_NB_KANJI = 1
WORDS_MIN_LENGTH = 1

CONFS = {
    "Very Easy": {
        "TARGET_KANJI_GRADE": 1,
        "INIT_HP": 50,
        "MAX_TIMER": 60,
        "HINT_TIME": 60,
    },
    "Easy": {
        "TARGET_KANJI_GRADE": 3,
        "INIT_HP": 10,
        "MAX_TIMER": 30,
        "HINT_TIME": 15,
    },
    "Normal": {
        "TARGET_KANJI_GRADE": 6,
        "INIT_HP": 10,
        "MAX_TIMER": 30,
        "HINT_TIME": 15,
    },
    "Hard": {
        "TARGET_KANJI_GRADE": 8,
        "INIT_HP": 10,
        "MAX_TIMER": 30,
        "HINT_TIME": 15,
    },
    "Expert": {
        "TARGET_KANJI_GRADE": 8,
        "INIT_HP": 5,
        "MAX_TIMER": 30,
        "HINT_TIME": -1,
    },
}

CONF_KEY_TO_TEXT = {
    "INIT_HP": "Number of lives (心)",
    "MAX_TIMER": "Time to guess a word",
    "HINT_TIME": "Hint appears at",
    "TARGET_KANJI_GRADE": "Target 常用漢字 grade",
}

DEFAULT_CONF_NAME = "Easy"
CONF = CONFS[DEFAULT_CONF_NAME]
CONF_KEYS = list(CONF.keys())


class Game:
    def __init__(self):
        pygame.init()
        pygame.font.init()
        pygame.display.init()

        # self.screen_w, self.screen_h = 1024, 768
        # self.screen_w, self.screen_h = 1280, 1024
        screen_ratio = 0.75
        self.screen_w = int(screen_ratio * pygame.display.Info().current_w)
        self.screen_h = int(screen_ratio * pygame.display.Info().current_h)
        self.screen = pygame.display.set_mode((self.screen_w, self.screen_h), pygame.RESIZABLE)
        pygame.display.set_caption("Kanji game - Press ESC to quit")

        font_family = get_font_family()
        self.small_font = pygame.font.SysFont(font_family, 24)
        self.font = pygame.font.SysFont(font_family, 48)
        self.large_font = pygame.font.SysFont(font_family, 80)

        self.clock = pygame.time.Clock()

        self.options_screen()

        self.loading_screen()

        self.user_input_value = ""
        self.free_joker = False
        self.clear_warning_msg()

        self.hp = CONF["INIT_HP"]
        self.combo = 0
        self.score = 0
        self.last_score_update = 0
        self.last_1up_score = 10

        self.running = True

        self.timer = CONF["MAX_TIMER"]

        self.init_candidate_kanjis()

        self.words = OrderedDict()

        kanjis = list(self.candidate_kanjis)
        self.kanji_to_match = random.choice(kanjis)
        self.update_joker_word()

        # DEBUG
        # self.kanji_to_match = "灰"
        # self.update_joker_word()

        # DEBUG
        # self.kanji_to_match = "小"
        # self.update_joker_word()

    def run(self):
        """Main loop"""

        while self.running:
            self.handle_events()
            self.process()
            self.render()

        self.dump_words()

        if self.hp == 0:
            self.game_over()

    def handle_events(self):
        self.validated_user_input = None
        events = pygame.event.get()
        for event in events:
            if exit_event(event):
                self.running = False
                return
            elif event.type == pygame.VIDEORESIZE:
                self.resize_screen(event.size)
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self.validated_user_input = self.user_input_value
                    self.user_input_value = ""
                    pygame.event.clear()
                    return
                elif event.key == pygame.K_BACKSPACE:
                    self.user_input_value = self.user_input_value[:-1]
                else:
                    key = event.unicode
                    if re.match("[a-z]", key):
                        self.user_input_value += key

    def resize_screen(self, size):
        old_screen = self.screen
        self.screen_w, self.screen_h = size
        print(f"Resizing window to {self.screen_w} x {self.screen_h})")
        self.screen = pygame.display.set_mode((self.screen_w, self.screen_h),
                                              pygame.RESIZABLE)
        # On the next line, if only part of the window
        # needs to be copied, there's some other options.
        self.screen.blit(old_screen, (0, 0))
        del old_screen
        pygame.display.update()

    def process(self):
        if not self.running:
            return

        # Remove the msg as soon as user started to type
        if self.user_input_value:
            self.clear_warning_msg()

        # Time up ?
        if self.timer == 0:
            self.set_warning_msg("Ran out of time ! Here is a word")
            self.lose_hp()
            # Special render to make the user wait !
            self.render_warning_msg()
            pygame.display.flip()

            self.add_word(self.joker_word, players_choice=False)
            pygame.event.clear()

        # Pressed Enter with an empty form ? Unstuck the player
        elif self.validated_user_input == "":
            if self.hp == 1 and not self.free_joker:
                self.set_warning_msg("Can't have a joker with only 心 left !")
            elif not self.joker_word:
                self.set_warning_msg("Sorry, no suggestion...")
            else:
                self.set_warning_msg("Giving up ? here is a word")
                if not self.free_joker:
                    self.lose_hp()

                # Special render to make the user wait !
                self.render_warning_msg()
                pygame.display.flip()

                self.add_word(self.joker_word, players_choice=False)
                self.free_joker = False

        # User validated a word proposal ?
        elif self.validated_user_input:
            self.process_validated_user_input()

        dt = self.clock.tick(30) / 1000
        self.timer -= dt
        if self.timer < 0:
            self.timer = 0

    def process_validated_user_input(self):
        higana_input = romkan.to_hiragana(self.validated_user_input)
        # Check there is only hiragana
        if re.match("[a-z]", higana_input):
            self.set_warning_msg("Invalid input !")
            return

        valid_entries_by_kanji_form, errors = self.lookup_word_entries(higana_input)

        if not valid_entries_by_kanji_form:
            if errors:
                # error message have a digit at the beginning, to get the most precise error
                error = sorted(errors)[0][1:]
                self.set_warning_msg(error)
            else:
                self.set_warning_msg("No match ! press Enter again to give up")
            self.lose_hp()
            self.free_joker = True
            return

        print(f"Found {len(valid_entries_by_kanji_form.keys())} valid entries for {higana_input}")
        for word in list(valid_entries_by_kanji_form.keys()):
            if word in self.words:
                print(f"Excluding word {word}: already used before")
                del valid_entries_by_kanji_form[word]

        if not valid_entries_by_kanji_form:
            self.set_warning_msg("Already used, try something else")
            return

        candidates = sorted(valid_entries_by_kanji_form.keys(), key=word_to_freqrank)

        if len(candidates) > 1:
            new_word = self.choose_word(candidates)
            if new_word is None:
                return
        else:
            new_word = candidates[0]
            # Special render to make the user wait !
            self.render_validated_word(new_word)
            pygame.display.flip()

        # Lose the free joker if any
        self.free_joker = False

        self.add_word(new_word)
        pygame.event.clear()  # FIXME: does not prevent "double taps"

    def lookup_word_entries(self, higana_input):
        valid_entries_by_kanji_form = {}
        errors = []

        lookup_res = JMD.lookup(higana_input,
                                strict_lookup=True, lookup_chars=False)
        print(f"Lookup result for {higana_input}:")
        for entry in lookup_res.entries:
            for kanji_form in entry.kanji_forms:
                word = str(kanji_form)
                is_valid, error = self.valid_word_candidate(word)
                if is_valid:
                    valid_entries_by_kanji_form[word] = entry
                    print(f"- {word}: OK")
                    break
                else:
                    print(f"- {word}: {error}")
                    errors.append(error)

        return valid_entries_by_kanji_form, errors

    def add_word(self, new_word, players_choice=True):
        previous_kanji = self.kanji_to_match

        # Remove the kanji to match from the list of kanjis to "collect"
        if (
                self.kanji_to_match in self.candidate_kanjis
                and (players_choice or ALWAYS_CLEAR_KANJI)
        ):
            self.clear_kanji_to_match()

        # Lookup the new word and add it to the history
        lookup_res = JMD.lookup(new_word, strict_lookup=True, lookup_chars=False)
        if not lookup_res.entries:
            raise Exception(f"No entry found for {new_word} !")
        entry = lookup_res.entries[0]
        print(f"Added word {new_word}　({entry.senses[0].text()}) "
              f"freqrank: {word_to_freqrank(new_word)}")
        self.words[new_word] = entry

        last_word = next(reversed(self.words))
        if MATCH_LAST_KANJI:
            self.kanji_to_match = last_word[-1]
        else:
            candidates = {kanji for kanji in last_word if
                          (kanji in self.candidate_kanjis and kanji != previous_kanji)}
            # If there are no kanjis for our level, pick a random kanji in the pool
            if not candidates:
                candidates = self.candidate_kanjis
            self.kanji_to_match = random.choice(list(candidates))

        has_possible_words = self.update_joker_word()
        if not has_possible_words:
            self.set_warning_msg(f"No words starting with {self.kanji_to_match}, here is a new one")
            self.pick_new_kanji_and_joker_word()

        self.update_score(players_choice, new_word, previous_kanji)

        # Reset the timer !
        self.timer = CONF["MAX_TIMER"]

    def clear_kanji_to_match(self):
        self.candidate_kanjis.remove(self.kanji_to_match)
        # Did we clear all the kanjis up to selected grade ?
        if not self.candidate_kanjis:
            # Increase the grade
            _kanjis_by_grade = kanjis_by_grade()

            CONF['TARGET_KANJI_GRADE'] = next_grade(CONF['TARGET_KANJI_GRADE'])

            if CONF['TARGET_KANJI_GRADE'] < MAX_KANJI_GRADE:
                new_kanjis = _kanjis_by_grade[CONF['TARGET_KANJI_GRADE']]
                self.candidate_kanjis.update(new_kanjis)
                self.init_nb_candidate_kanjis += len(self.candidate_kanjis)
            else:
                # Restart from beginning: all the kanjis must be cleared again
                CONF['TARGET_KANJI_GRADE'] = MAX_KANJI_GRADE
                self.candidate_kanjis.update(self.valid_kanjis)

    def update_score(self, players_choice, new_word, previous_kanji):
        if not players_choice:
            self.last_score_update = 0
            return

        score_update = self.compute_score_update(new_word, previous_kanji)
        self.score += score_update
        self.last_score_update = score_update
        msg = f"正解！　+{score_update}点"

        bonus_hp = 0
        while self.score > self.last_1up_score:
            bonus_hp += 1
            self.last_1up_score *= 2

        if bonus_hp:
            self.hp += bonus_hp
            msg = f"{msg}, +{bonus_hp}心 (次:{self.last_1up_score * 2}点)"

        self.set_warning_msg(msg, color=YELLOW)

    def update_joker_word(self) -> bool:
        print("Look for a joker word with only candidate kanjis")
        self.joker_word = self.find_one_valid_word()

        # No more words ending with one of the remaining kanjis to match ?
        # Get one outside these kanjis !
        if not self.joker_word:
            print("No word with a candidate kanjis, look for any word with the kanji to match")
            self.joker_word = self.find_one_valid_word(candidate_kanjis_only=False)

        # No word matching at all ?
        if not self.joker_word:
            return False

        self.joker_word_sense = get_word_meaning(self.joker_word)
        print(f"Joker is {self.joker_word} ({self.joker_word_sense})")
        return True

    def compute_score_update(self, new_word, previous_kanji):
        self.combo += 1
        grade_scores = self.compute_word_grade_scores(new_word, previous_kanji)
        total_grade_score = sum(grade_scores)
        no_hint_multiplier = 2 if (self.timer > CONF["HINT_TIME"]) else 1
        score_update = total_grade_score * no_hint_multiplier * self.combo
        print(
            f"Score += ({'+'.join(map(str, grade_scores))}★) "
            f"ｘ ({self.combo}◎) x ({no_hint_multiplier} タイマ)")
        return score_update

    def compute_word_grade_scores(self, word, previous_kanji):
        scores = []
        for char in word:
            # Only reward for the "new" kanjis
            if (
                    char == previous_kanji or
                    (char in self.valid_kanjis and char not in self.candidate_kanjis)
            ):
                grade = int(JMD.get_char(char).grade)
                scores.append(KANJI_GRADE_TO_INFO[grade]['score'])
        return scores

    def clear_warning_msg(self):
        self.warning_msg = None
        self.warning_msg_start_ts = None

    def set_warning_msg(self, new_msg, color=RED):
        self.warning_msg = new_msg
        self.warning_msg_start_ts = time.time()
        self.warning_msg_color = color

    def render(self):
        self.screen.fill(0)

        self.render_top_pane()
        self.render_words()
        self.render_hint()
        self.render_prompt()
        self.render_kanjis_counter()
        self.render_combo_jauge()
        self.render_warning_msg()

        pygame.display.flip()

    def render_top_pane(self):
        self.render_hps()
        self.render_timer()
        self.render_score()

    def render_hps(self):
        hp_str = "心ｘ" + str(self.hp).ljust(2)
        color = WHITE if self.hp > 1 else RED
        hp_surf = self.font.render(hp_str, True, color)
        self.hp_rect = hp_surf.get_rect(topleft=(0, 0))
        self.screen.blit(hp_surf, self.hp_rect)

    def render_timer(self):
        timer_str = f"タイマ：{str(int(self.timer)).zfill(2)}　"
        if self.timer <= 5:
            color = RED
        elif self.timer < CONF["MAX_TIMER"] / 2:
            color = YELLOW
        else:
            color = WHITE
        timer_surf = self.font.render(timer_str, True, color)
        timer_rect = timer_surf.get_rect(top=0, centerx=self.screen_w / 2)
        self.screen.blit(timer_surf, timer_rect)

    def render_score(self):
        text, color = format_score(self.score, self.last_score_update, self.timer)
        score_surf = self.font.render(text, True, color)
        score_rect = score_surf.get_rect(top=0, right=self.screen_w)
        self.screen.blit(score_surf, score_rect)

    def render_words(self):
        nb_words_to_show = 5
        last_words = list(self.words.keys())[-nb_words_to_show:]
        # Padding to get nb_to_show words
        padding = (nb_words_to_show - len(last_words)) * ['']
        words = padding + last_words

        top = self.hp_rect.bottom
        for idx, word in enumerate(words):
            alpha = int((len(words) - idx) / len(words) * 150)
            self.render_word(word, top, alpha)
            text_height = self.words_surf.get_height()
            top += text_height

        color = GREEN if self.combo > 0 else WHITE
        word_question = self.kanji_to_match + "？"
        self.words_surf = self.large_font.render(word_question, True, color)
        self.words_rect = self.words_surf.get_rect(top=top)
        self.screen.blit(self.words_surf, self.words_rect)

        meaning, grade = kanji_meaning_and_grade(self.kanji_to_match)
        meaning_surf = self.small_font.render(meaning, True, color)
        meaning_rect = meaning_surf.get_rect(topleft=self.words_rect.topright)
        self.screen.blit(meaning_surf, meaning_rect)

        grade_surf = self.small_font.render(grade_text(grade), True, GRAY)
        grade_rect = grade_surf.get_rect(topleft=meaning_rect.bottomleft)
        self.screen.blit(grade_surf, grade_rect)

    def render_word(self, word, top, alpha):
        self.words_surf = self.font.render(word, True, BLUE)
        self.words_rect = self.words_surf.get_rect(top=top)
        self.screen.blit(self.words_surf, self.words_rect)

        if len(word) > 0:
            entry = self.words[word]
            furigana = str(entry.kana_forms[0])
            furigana_surf = self.small_font.render("　" + furigana, True, BLUE)
            furigana_rect = furigana_surf.get_rect(topleft=self.words_rect.topright)
            self.screen.blit(furigana_surf, furigana_rect)

            sense = entry.senses[0].text()
            sense_surf = self.small_font.render("　" + sense, True, BLUE)
            sense_rect = sense_surf.get_rect(topleft=furigana_rect.topright)
            self.screen.blit(sense_surf, sense_rect)

        alpha_surf = pygame.Surface((self.screen_w, self.words_surf.get_height()))
        alpha_surf.fill(0)
        alpha_surf.set_alpha(alpha)
        self.screen.blit(alpha_surf, (0, top))

    def render_hint(self):
        if self.timer < CONF["HINT_TIME"] and self.joker_word_sense:
            hint_str = "ヒント：" + self.joker_word_sense
            hint_surf = self.small_font.render(hint_str, True, WHITE)
            hint_rect = hint_surf.get_rect(topleft=self.words_rect.bottomleft)
            self.screen.blit(hint_surf, hint_rect)

    def render_validated_word(self, word):
        text = word
        surf = self.large_font.render(text, True, WHITE)
        rect = surf.get_rect(topleft=self.words_rect.bottomleft)
        self.screen.fill(0, rect)
        self.screen.blit(surf, rect)

    def render_warning_msg(self):
        if self.warning_msg:
            fade_threshold = 1
            ellapsed = time.time() - self.warning_msg_start_ts
            if ellapsed > fade_threshold:
                alpha = min((ellapsed - fade_threshold) * 255, 255)
            else:
                alpha = 0

            if alpha >= 255:
                return

            warning_msg_surf = self.font.render(self.warning_msg, True, self.warning_msg_color)
            warning_msg_rect = warning_msg_surf.get_rect(bottomleft=self.prompt_rect.topleft)
            black_surf = pygame.Surface((self.screen_w, warning_msg_surf.get_height()))
            black_surf.fill(0)
            self.screen.blit(black_surf, warning_msg_rect)
            self.screen.blit(warning_msg_surf, warning_msg_rect)
            black_surf.set_alpha(alpha)
            self.screen.blit(black_surf, warning_msg_rect)

    def render_prompt(self):
        self.prompt = self.large_font.render('>', True, BLUE)
        self.prompt_rect = self.prompt.get_rect(bottomleft=(0, self.screen_h))
        self.screen.blit(self.prompt, self.prompt_rect)

        if self.user_input_value:
            text = romkan.to_hiragana(self.user_input_value)
            color = GREEN
        else:  #elif not self.words:
            # First kanji ? show a message to help new players
            text = f"Type a word with {self.kanji_to_match}"
            color = GRAY
        # else:
        #     text = ""
        #     color = GREEN

        self.user_input = self.large_font.render(text, True, color)
        self.user_input_rect = self.user_input.get_rect(topleft=self.prompt_rect.topright)
        self.screen.blit(self.user_input, self.user_input_rect)

    def render_kanjis_counter(self):
        bottom = self.prompt_rect.top
        right = self.screen_w
        text = self.kanjis_counter_text()
        kanjis_counter_surf = self.small_font.render(text, True, WHITE)
        self.kanjis_counter_rect = kanjis_counter_surf.get_rect(bottom=bottom, right=right)
        self.screen.blit(kanjis_counter_surf, self.kanjis_counter_rect)

    def kanjis_counter_text(self):
        grade_score = KANJI_GRADE_TO_INFO[CONF['TARGET_KANJI_GRADE']]['score']
        return (
            f"{grade_score * '★'}漢字 "
            f"{len(self.candidate_kanjis)}／{self.init_nb_candidate_kanjis}"
        )

    def render_combo_jauge(self):
        top = self.hp_rect.bottom
        right = self.screen_w
        for _ in range(self.combo):
            combo_surf = self.small_font.render("◎", True, YELLOW)
            combo_rect = combo_surf.get_rect(top=top, right=right)
            self.screen.blit(combo_surf, combo_rect)
            text_height = combo_surf.get_height()
            top += text_height
            if top + text_height >= self.kanjis_counter_rect.top:
                top = self.hp_rect.bottom
                right -= combo_surf.get_width()

    def choose_word(self, candidates: List[str]) -> Optional[str]:
        cursor = 0
        done = False
        cancel = False
        while not done:
            events = pygame.event.get()
            for event in events:
                if exit_event(event):
                    self.running = False
                    done = True
                    break
                elif event.type == pygame.VIDEORESIZE:
                    self.resize_screen(event.size)
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        done = True
                        cancel = True
                        break
                    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        print(f"You chose {candidates[cursor]}")
                        done = True
                        break
                    elif event.key == pygame.K_UP:
                        cursor -= 1
                        if cursor < 0:
                            cursor = len(candidates) - 1
                        break
                    elif event.key == pygame.K_DOWN:
                        cursor += 1
                        if cursor >= len(candidates):
                            cursor = 0
                        break

            self.render_choose_word(candidates, cursor)

        if not cancel:
            self.render_choose_word(candidates, cursor, only_selection=True)
            return candidates[cursor]
        else:
            return None

    def render_choose_word(self, candidates, cursor, only_selection=False):
        top = self.words_rect.bottom

        surf = self.font.render("Choose a word using ↑, ↓ and Enter", True, WHITE)
        rect = surf.get_rect(top=top, left=0)
        self.screen.fill(0, rect)
        if not only_selection:
            self.screen.blit(surf, rect)
        top += surf.get_height()

        for idx, word in enumerate(candidates):
            cursor_txt = ">" if idx == cursor and not only_selection else " "
            cursor_surf = self.large_font.render(cursor_txt, True, GREEN)
            cursor_rect = cursor_surf.get_rect(top=top, left=0)
            self.screen.fill(0, cursor_rect)
            self.screen.blit(cursor_surf, cursor_rect)

            color = GREEN if idx == cursor else GRAY
            surf = self.large_font.render(word, True, color)
            rect = surf.get_rect(top=top, left=cursor_rect.right)

            self.screen.fill(0, rect)
            if idx == cursor or not only_selection:
                self.screen.blit(surf, rect)

            top += surf.get_height()

        pygame.display.flip()
        self.clock.tick(30)

    def options_screen(self):
        global CONF
        modes = list(CONFS.keys())
        cursor = 0
        while True:
            events = pygame.event.get()
            for event in events:
                if exit_event(event):
                    pygame.quit()
                    sys.exit(0)
                elif event.type == pygame.VIDEORESIZE:
                    self.resize_screen(event.size)
                elif event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        CONF = CONFS[modes[cursor]]
                        return
                    elif event.key == pygame.K_LEFT:
                        cursor -= 1
                        if cursor < 0:
                            cursor = len(modes) - 1
                        break
                    elif event.key == pygame.K_RIGHT:
                        cursor += 1
                        if cursor >= len(modes):
                            cursor = 0
                        break

            self.render_options_screen(modes, cursor)

    def render_options_screen(self, modes, cursor):

        self.screen.fill(0)
        top = 0

        surf = self.font.render(f"Choose difficulty with ← and →, then press Enter", True, WHITE)
        rect = surf.get_rect(top=top, left=0)
        self.screen.blit(surf, rect)
        top += surf.get_height()

        surf = self.large_font.render(f"Difficulty: < {modes[cursor].ljust(10)} >", True, YELLOW)
        rect = surf.get_rect(top=top, left=0)
        self.screen.blit(surf, rect)
        top += 2 * surf.get_height()

        conf = CONFS[modes[cursor]]
        for conf_key in CONF_KEYS:
            key_text, value_text = conf_item_to_text(conf, conf_key)
            text = f"{key_text}: {value_text}"
            surf = self.font.render(text, True, GRAY)
            rect = surf.get_rect(top=top, left=0)
            self.screen.blit(surf, rect)
            top += surf.get_height()

        pygame.display.flip()
        self.clock.tick(30)

    def loading_screen(self):
        self.screen.fill(0)
        loading = self.large_font.render('読み込み中...', True, GREEN)
        loading_rect = loading.get_rect()
        loading_rect.center = (self.screen_w / 2, self.screen_h / 2)
        self.screen.blit(loading, loading_rect)
        pygame.display.flip()

    def dump_words(self):
        if not self.words:
            return

        with open("log", "w") as outfile:
            print(f"Score: {self.score}", file=outfile)
            print(self.kanjis_counter_text(), file=outfile)
            rarest_word = sorted(self.words.keys(), key=word_to_freqrank)[-1]
            rarest_entry = self.words[rarest_word]
            print(f"Rarest word: {rarest_word} {rarest_entry.kana_forms[0]} "
                  f"{rarest_entry.senses[0].text()}",
                  file=outfile)

            print("Words list:", file=outfile)
            for word, entry in self.words.items():
                print(f"- {word} {entry.kana_forms[0]} {entry.senses[0].text()}", file=outfile)

    def game_over(self):
        # Fade the screen
        alpha_surf = pygame.Surface((self.screen_w, self.screen_h))
        alpha_surf.fill(0)
        alpha_surf.set_alpha(200)
        self.screen.blit(alpha_surf, (0, 0))

        # Show "the end"
        surf = self.large_font.render("終", True, RED)
        rect = surf.get_rect()
        rect.center = (self.screen_w / 2, self.screen_h / 2)
        self.screen.blit(surf, rect)

        pygame.display.flip()

        time.sleep(1)

        # Wait for user to press any key
        while True:
            events = pygame.event.get()
            for event in events:
                if exit_event(event) or event.type == pygame.KEYDOWN:
                    return
            self.clock.tick(30)

    def init_candidate_kanjis(self):
        _kanjis_by_grade = kanjis_by_grade()

        self.candidate_kanjis = set()
        self.valid_kanjis = set()
        for grade in KANJI_GRADES:
            self.valid_kanjis.update(_kanjis_by_grade[grade])
            if grade <= CONF['TARGET_KANJI_GRADE']:
                self.candidate_kanjis.update(_kanjis_by_grade[grade])

        self.init_nb_candidate_kanjis = len(self.candidate_kanjis)

    def pick_new_kanji_and_joker_word(self):
        kanjis = list(self.candidate_kanjis)
        while True:
            self.kanji_to_match = random.choice(kanjis)
            has_possible_words = self.update_joker_word()
            if has_possible_words:
                return
            # Could not find any valid word with that kanji, will try another
            print(f"Could not find a word starting with {self.kanji_to_match} !")
            kanjis.remove(self.kanji_to_match)

    def find_one_valid_word(self, candidate_kanjis_only=True):
        candidate_words = set()
        query = f"{self.kanji_to_match}%" if MATCH_LAST_KANJI else f"%{self.kanji_to_match}%"
        lookup_res = JMD.lookup(query, strict_lookup=True, lookup_chars=False)
        for entry in lookup_res.entries:
            for kanji_form in entry.kanji_forms:
                word = str(kanji_form)
                if word in self.words:
                    # Don't want already seen words
                    continue
                is_valid, _ = self.valid_word_candidate(word)
                if is_valid:
                    # Avoid kanjis that are not outside our grade
                    if (
                            candidate_kanjis_only is False
                            or not any((
                            kanji in self.valid_kanjis and kanji not in self.candidate_kanjis
                            for kanji in word
                    ))
                    ):
                        candidate_words.add(word)

        if candidate_words:
            print(f"Found {len(candidate_words)} possible words for {self.kanji_to_match}")
            word_freqrank_pairs = []
            for word in candidate_words:
                freqrank = word_to_freqrank(word)
                if freqrank != sys.maxsize:
                    word_freqrank_pairs.append((word, freqrank))

            if word_freqrank_pairs:
                sorted_words = sorted(word_freqrank_pairs, key=operator.itemgetter(1))
                for word, freqrank in sorted_words[:10]:
                    print(f"- {word} ({freqrank})")
                # Randomize a bit
                return random.choice(sorted_words[:JOKER_WORD_POOL_SIZE])[0]
            else:
                return random.choice(list(candidate_words))

        return None

    def lose_hp(self):
        self.hp -= 1
        self.combo = 0
        # Game over ?
        if self.hp == 0:
            self.running = False

    def valid_word_candidate(self, word):
        if MATCH_LAST_KANJI and not word.startswith(self.kanji_to_match):
            return False, f'4 Word must start with {self.kanji_to_match}'
        if self.kanji_to_match not in word:
            return False, f'3 Word must contain {self.kanji_to_match}'
        if len(word) < WORDS_MIN_LENGTH:
            return False, f'2 Word must be {WORDS_MIN_LENGTH}+ character'

        kanjis = self.get_word_kanjis(word)

        if len(kanjis) < WORDS_MIN_NB_KANJI:
            return False, f'1 Word must contain {WORDS_MIN_NB_KANJI}+ kanji'

        return True, None

    def get_word_kanjis(self, word):
        kanjis = []
        for char in word:
            if char in self.valid_kanjis:
                kanjis.append(char)
        return kanjis


def get_word_meaning(word):
    lookup_res = JMD.lookup(word, strict_lookup=True, lookup_chars=False)
    if not lookup_res.entries:
        raise Exception(f"No entry found for {word} !")
    entry = lookup_res.entries[0]
    return entry.senses[0].text()


def kanji_meaning_and_grade(kanji):
    entry = JMD.get_char(kanji)
    meaning = ", ".join((m.value for m in entry.rm_groups[0].meanings if m.m_lang == ''))
    grade = int(entry.grade) if entry.grade else None
    return meaning, grade


def grade_text(grade):
    if grade is None:
        return f"No grade"
    info = KANJI_GRADE_TO_INFO.get(grade)
    if info:
        return f'{info["score"] * "★"} {info["desc"]}'
    raise Exception(f"Grade {grade} is not used in the game !")


def next_grade(grade):
    idx = KANJI_GRADES.index(grade)
    if idx == len(KANJI_GRADES) - 1:
        return idx
    return idx + 1


def kanjis_by_grade():
    def compute_kanjis_by_grade():
        _kanjis_by_grade = defaultdict(set)
        for kanji in JMD.kd2_xml.char_map.values():
            if kanji.grade is not None:
                _kanjis_by_grade[int(kanji.grade)].add(kanji.literal)
        return _kanjis_by_grade

    cache_filepath = "data/kanjis_grade"

    if os.path.isfile(cache_filepath):
        print("Loading kanjis from cache")
        with open(cache_filepath, "rb") as cache_file:
            _kanjis_by_grade = pickle.load(cache_file)

    else:
        print("Save kanjis to cache")
        _kanjis_by_grade = compute_kanjis_by_grade()
        with open(cache_filepath, "wb") as cache_file:
            pickle.dump(_kanjis_by_grade, cache_file)

    return _kanjis_by_grade


def format_score(score, last_score_update, timer):
    score_padding = 5
    big_score = score >= 10 ** score_padding
    if big_score:
        score_padding = score_padding + 4

    # Temporarily show the update instead of the total ?
    if CONF["MAX_TIMER"] - timer < 3 and last_score_update:
        text = ("+" + str(last_score_update)).rjust(score_padding)
        color = YELLOW
    else:
        text = str(score).rjust(score_padding)
        color = WHITE

    if big_score:
        text = f"S:{text}"
    else:
        text = f"SCORE:{text}"
    return text, color


def conf_item_to_text(conf, conf_key):
    key_text = CONF_KEY_TO_TEXT[conf_key]
    value = conf.get(conf_key)
    if value is None:
        value_text = 'N/A'
    elif conf_key == "MAX_TIMER":
        value_text = f"{value}s"
    elif conf_key == "HINT_TIME":
        if value >= 0:
            value_text = f"{value}s"
        else:
            value_text = f"Never"
    elif conf_key == "TARGET_KANJI_GRADE":
        value_text = grade_text(value)
    else:
        value_text = str(value)

    return key_text, value_text


def get_font_family():
    installed_fonts = set(pygame.font.get_fonts())
    candidate_fonts = ["umegothic", "notosanscjkjp", "takaogothic", "takaomincho"]
    for font in candidate_fonts:
        if font in installed_fonts:
            return font
    raise Exception(
        "Could not find a proper font to display Japanese characters ! "
        "See the following page for instructions on how to install them: "
        "https://en.wikipedia.org/wiki/Help:Installing_Japanese_character_sets"
    )


def exit_event(event):
    return (
        event.type == pygame.QUIT or
        (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE)
    )


def main():
    Game().run()


if __name__ == "__main__":
    main()
