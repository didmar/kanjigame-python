Kanji game
===========

An educational game to practice kanji-based Japanese words.

Why ?
---------------

Japanese kanjis are notoriously hard to learn.
In order to master them, a lot of practice is inevitable.

Among kanji-based words, compound words of Chinese origin have a lot of homonyms,
which can make them hard to memorize. Here is an example:

    大綱　taikou—a large rope;
    対抗　taikou—opposition;
    大公　taikou—an archduke;
    対向　taikou—the opposite direction;
    退校　taikou—expulsion from school;
    体腔　taikou—body cavity

This game was designed to help Japanese language learners practice those words in a fun way ! 

How to install
---------------

Install the Python requirements:
```sh
pip3 install -r requirements.txt
```

Then, run the following script to download the dictionary files and import them 
```sh
./download_dicts.sh
```

Finally, you can run the game:
```sh
python3 -m kanjigame
```

Game rules
-----------

The goal is to find words composed of kanjis and matching a kanji given by the game.

Type a word matching a kanji, before the timer runs out, to score some points.
A new kanji is then drawn, considering the kanji level you aim for
(school grades of 常用漢字).

If the timer runs out or your answer is invalid, you will lose one life (心).
After this, you may get an automatically generated answer to move on to a new kanji.

To get the best score, try to make a "chain", for example 仕事, 事故, 故障, ...
This will increase the kanji combo multiplier ! 