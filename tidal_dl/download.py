#!/usr/bin/env python
# -*- encoding: utf-8 -*-
'''
@File    :   download.py
@Time    :   2020/11/08
@Author  :   Yaronzz
@Version :   1.0
@Contact :   yaronhuang@foxmail.com
@Desc    :   
'''

from time import sleep
import logging
import os
import shutil
import zipfile 

from bot import LOGGER, Config
from bot.helpers.translations import lang

import aigpy
import tidal_dl
from tidal_dl.enums import Type
from tidal_dl.model import Mix
from tidal_dl.printf import Printf
from tidal_dl.util import downloadTrack, downloadVideo, getAlbumPath, API

from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def __loadAPI__(user):
    API.key.accessToken = user.accessToken
    API.key.userId = user.userid
    API.key.countryCode = user.countryCode

async def __downloadCover__(conf, album, reply_to_id=None):
    if album == None:
        return
    if reply_to_id:
        path = Config.DOWNLOAD_BASE_DIR + f"/thumb/{reply_to_id}.jpg"
    else:
        path = await getAlbumPath(conf, album) + '/cover.jpg'
    url = API.getCoverUrl(album.cover, "80", "80")
    logging.info(f"Downloading cover: {url}")
    if url is not None:
        aigpy.net.downloadFile(url, path)

async def post_album_details(album, bot, chat_id, reply_to_id):
    album_art_path = Config.DOWNLOAD_BASE_DIR + f"/thumb/{reply_to_id}-ALBUM.jpg"
    album_art = API.getCoverUrl(album.cover, "1280", "1280")
    if album_art is not None:
        aigpy.net.downloadFile(album_art, album_art_path)
        photo = await bot.send_photo(
            chat_id=chat_id,
            photo=album_art_path,
            caption=lang.ALBUM_DETAILS.format(
                album.title,
                album.artist.name,
                album.releaseDate,
                album.numberOfTracks,
                album.duration,
                album.numberOfVolumes
            ),
            reply_to_message_id=reply_to_id
        )
        if Config.ALLOW_DUMP:
            photo.copy(
                chat_id=Config.LOG_CHANNEL_ID,
            )
        os.remove(album_art_path)

async def __saveAlbumInfo__(conf, album, tracks):
    if album == None:
        return
    path = await getAlbumPath(conf, album) + '/AlbumInfo.txt'

    infos = ""
    infos += "[ID]          %s\n" % (str(album.id))
    infos += "[Title]       %s\n" % (str(album.title))
    infos += "[Artists]     %s\n" % (str(album.artist.name))
    infos += "[ReleaseDate] %s\n" % (str(album.releaseDate))
    infos += "[SongNum]     %s\n" % (str(album.numberOfTracks))
    infos += "[Duration]    %s\n" % (str(album.duration))
    infos += '\n'

    i = 0
    while True:
        if i >= int(album.numberOfVolumes):
            break
        i = i + 1
        infos += "===========CD %d=============\n" % i
        for item in tracks:
            if item.volumeNumber != i:
                continue
            infos += '{:<8}'.format("[%d]" % item.trackNumber)
            infos += "%s\n" % item.title
    aigpy.file.write(path, infos, "w+")


async def __album__(conf, obj, bot, chat_id, reply_to_id, zipit):
    msg, tracks, videos = API.getItems(obj.id, Type.Album)
    if not aigpy.string.isNull(msg):
        return
    if conf.saveAlbumInfo:
        await __saveAlbumInfo__(conf, obj, tracks)
    await post_album_details(obj, bot, chat_id, reply_to_id)
    for item in tracks:
        if conf.saveCovers:
            await __downloadCover__(conf, obj, reply_to_id)
        await downloadTrack(item, obj, bot=bot, chat_id=chat_id, reply_to_id=reply_to_id, zipit=zipit)
        sleep(1)
    """for item in videos:
        downloadVideo(item, obj)"""


async def __track__(conf, obj, bot, chat_id, reply_to_id):
    msg, album = API.getAlbum(obj.album.id)
    if conf.saveCovers:
        await __downloadCover__(conf, album, reply_to_id)
    await downloadTrack(obj, album, bot=bot, chat_id=chat_id, reply_to_id=reply_to_id, zipit=False)


async def __video__(conf, obj, bot, chat_id, reply_to_id):
    downloadVideo(obj, obj.album)


async def __artist__(conf, obj, bot, chat_id, reply_to_id, zipit):
    msg, albums = API.getArtistAlbums(obj.id, conf.includeEP)
    #Printf.artist(obj, len(albums))
    if not aigpy.string.isNull(msg):
        return
    for item in albums:
        await __album__(conf, item, bot, chat_id, reply_to_id, zipit)


async def __playlist__(conf, obj, bot, chat_id, reply_to_id, zipit):
    msg, tracks, videos = API.getItems(obj.uuid, Type.Playlist)
    if not aigpy.string.isNull(msg):
        return

    for index, item in enumerate(tracks):
        mag, album = API.getAlbum(item.album.id)
        item.trackNumberOnPlaylist = index + 1
        await downloadTrack(item, album, obj, bot=bot, chat_id=chat_id, reply_to_id=reply_to_id, zipit=zipit)
        if conf.saveCovers and not conf.usePlaylistFolder:
            await __downloadCover__(conf, album, reply_to_id)

        

async def __mix__(conf, obj: Mix, bot, chat_id, reply_to_id, zipit):
    for index, item in enumerate(obj.tracks):
        mag, album = API.getAlbum(item.album.id)
        item.trackNumberOnPlaylist = index + 1
        await downloadTrack(item, album, bot=bot, chat_id=chat_id, reply_to_id=reply_to_id, zipit=zipit)
        if conf.saveCovers and not conf.usePlaylistFolder:
            await __downloadCover__(conf, album, reply_to_id)

async def file(user, conf, string):
    txt = aigpy.file.getContent(string)
    if aigpy.string.isNull(txt):
        return
    array = txt.split('\n')
    for item in array:
        if aigpy.string.isNull(item):
            continue
        if item[0] == '#':
            continue
        if item[0] == '[':
            continue
        await start(user, conf, item)


async def start(user, conf, string, bot=None, chat_id=None, reply_to_id=None, zipit=None):
    __loadAPI__(user)
    if aigpy.string.isNull(string):
        return

    is_authed = tidal_dl.checkLogin()
    if not is_authed:
        return await bot.edit_message_text(
            chat_id=chat_id,
            message_id=reply_to_id,
            text=lang.AUTH_DISABLED
        )
    strings = string.split(" ")
    for item in strings:
        if aigpy.string.isNull(item):
            continue
        if os.path.exists(item):
            file(user, conf, item)
            return

        msg, etype, obj = API.getByString(item)
        if etype == Type.Null or not aigpy.string.isNull(msg):
            Printf.err(msg + " [" + item + "]")
            return

        
        if etype == Type.Track:
            await __track__(conf, obj, bot, chat_id, reply_to_id)
        elif zipit == None:
            await bot.send_message(
                chat_id=chat_id,
                text=lang.WAIT_UPLOAD_MODE,
                reply_to_message_id=reply_to_id,
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                text="All songs in ZIP",
                                callback_data="z_" + string
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                text="All songs to TG Seperately",
                                callback_data="t_" + string
                            )
                        ]
                    ]
                )
            )
        else:
            if zipit == "allowed":
                zip_dir = Config.DOWNLOAD_BASE_DIR + "/" + str(reply_to_id)
                os.makedirs(zip_dir, exist_ok=True)
            if etype == Type.Album:
                await __album__(conf, obj, bot, chat_id, reply_to_id, zipit)
            if etype == Type.Artist:
                await __artist__(conf, obj, bot, chat_id, reply_to_id, zipit)
            if etype == Type.Playlist:
                await __playlist__(conf, obj, bot, chat_id, reply_to_id, zipit)
            if etype == Type.Mix:
                await __mix__(conf, obj, bot, chat_id, reply_to_id, zipit)
            if zipit == "allowed":
                LOGGER.info("Zipping Started")
                to_be_zipped_dir = Config.DOWNLOAD_BASE_DIR + "/" + str(reply_to_id) + "/"
                zip_file_name = to_be_zipped_dir + "/" + obj.title
                if os.path.exists(zip_file_name):
                    os.remove(zip_file_name)
                zipf = zipfile.ZipFile(zip_file_name, 'w', zipfile.ZIP_DEFLATED)
                for files in os.listdir(to_be_zipped_dir):
                    zipf.write(os.path.join(to_be_zipped_dir, files), files)
                zipf.close()

                #shutil.make_archive(zip_file_name, 'zip', to_be_zipped_dir)
                await bot.send_document(
                    chat_id=chat_id,
                    document=zip_file_name + ".zip",
                    reply_to_message_id=reply_to_id
                )
