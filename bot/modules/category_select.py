from pyrogram.handlers import CallbackQueryHandler
from pyrogram.filters import regex
from copy import deepcopy

from bot import bot, categories_dict
from bot.modules.mirror_leech import _mirror_leech
from bot.helper.telegram_helper.message_utils import editMessage

async def _get_filename_from_msg(message):
    """Mencoba mendapatkan nama file dari pesan asli."""
    if reply := message.reply_to_message:
        # Jika pesan adalah balasan ke file media
        if file_obj := getattr(reply, reply.media.value, None):
            return getattr(file_obj, "file_name", None)
        # Jika pesan adalah balasan ke teks (kemungkinan berisi link)
        elif reply.text:
            from urllib.parse import unquote
            from os.path import basename
            link = reply.text.split('\n', 1)[0].strip()
            if link:
                # Mengambil nama file dari bagian akhir URL
                return unquote(basename(link.split("?")[0]))
    # Jika link ada di dalam teks perintah itu sendiri
    elif " " in message.text:
        from urllib.parse import unquote
        from os.path import basename
        link = message.text.split(" ", 1)[1].strip()
        if link:
            # Mengambil nama file dari bagian akhir URL
            return unquote(basename(link.split("?")[0]))
    return None

async def select_category(client, query):
    """Menangani callback saat tombol kategori folder ditekan."""
    user_id = query.from_user.id
    data = query.data.split()

    # Memastikan tombol ditekan oleh pengguna yang benar
    if user_id != int(data[1]):
        return await query.answer(text="Bukan milikmu!", show_alert=True)

    # Menangani jika pengguna membatalkan
    if len(data) > 2 and data[2] == "cncl":
        await editMessage(query.message, "Tugas telah dibatalkan.")
        return

    # Mendapatkan nama dan ID drive dari data tombol
    cat_name = data[2].replace("_", " ")
    drive_id = categories_dict[cat_name]['drive_id']
    index_link = categories_dict[cat_name].get('index_link')

    await query.answer()

    # Mendapatkan pesan perintah asli (/mirror, /leech, dll.)
    cmd_message = query.message.reply_to_message
    
    # Mendapatkan nama file awal dari pesan perintah
    file_name = await _get_filename_from_msg(cmd_message)

    # Membuat pesan konfirmasi dinamis
    if file_name:
        msg = f"✅ Oke! File <b><code>{file_name}</code></b> akan di-mirror ke folder 💿 <b>{cat_name}</b>."
    else:
        msg = f"✅ Oke! File akan di-mirror ke folder 💿 <b>{cat_name}</b>."
    
    await editMessage(query.message, msg)
    
    # Membuat salinan dari pesan asli untuk dimodifikasi
    new_message = deepcopy(cmd_message)
    
    # Menambahkan argumen drive_id dan index_link ke perintah
    new_message.text += f' -id "{drive_id}"'
    if index_link:
        new_message.text += f' -index "{index_link}"'

    # Menjalankan kembali fungsi mirror/leech dengan argumen baru
    # Perlu menggunakan 'client' dari 'query' untuk memastikan konteks pengguna yang benar
    await _mirror_leech(client, new_message)

# Menambahkan handler ke bot agar fungsi di atas bisa dipanggil
# Regex "scat" digunakan untuk mengidentifikasi tombol kategori
scat_handler = CallbackQueryHandler(select_category, filters=regex(r"^scat"))
bot.add_handler(scat_handler)
