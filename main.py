import os
import io
import logging
from pathlib import Path
from typing import Dict, Tuple, Optional

from PIL import Image
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middleware.logging import LoggingMiddleware
from aiogram.types import ParseMode, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize bot and dispatcher
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# Supported formats
SUPPORTED_FORMATS: Dict[str, Tuple[str, str]] = {
    "png": ("PNG", "image/png"),
    "jpg": ("JPEG", "image/jpeg"),
    "jpeg": ("JPEG", "image/jpeg"),
    "webp": ("WEBP", "image/webp"),
    "gif": ("GIF", "image/gif"),
    "bmp": ("BMP", "image/bmp"),
    "tiff": ("TIFF", "image/tiff"),
    "ico": ("ICO", "image/x-icon")
}

# User state management
user_states: Dict[int, Dict] = {}

# ==================== Helper Functions ====================

def get_format_buttons() -> InlineKeyboardMarkup:
    """Generate inline keyboard with supported formats"""
    buttons = []
    row = []
    
    for idx, fmt in enumerate(SUPPORTED_FORMATS.keys()):
        row.append(InlineKeyboardButton(fmt.upper(), callback_data=f"format_{fmt}"))
        if len(row) == 4:  # 4 buttons per row
            buttons.append(row)
            row = []
    
    if row:
        buttons.append(row)
    
    # Add cancel button
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def convert_image(
    image_bytes: bytes,
    input_format: str,
    output_format: str,
    quality: int = 95
) -> Optional[bytes]:
    """
    Convert image from one format to another
    
    Args:
        image_bytes: Raw image bytes
        input_format: Source format (e.g., 'png')
        output_format: Target format (e.g., 'jpg')
        quality: JPEG/WEBP quality (1-100)
    
    Returns:
        Converted image bytes or None if conversion fails
    """
    try:
        # Open image
        image = Image.open(io.BytesIO(image_bytes))
        
        # Convert RGBA to RGB for JPEG (doesn't support alpha)
        if output_format.lower() in ['jpg', 'jpeg'] and image.mode == 'RGBA':
            # Create white background
            background = Image.new('RGB', image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[3])  # Use alpha channel as mask
            image = background
        elif output_format.lower() in ['jpg', 'jpeg'] and image.mode not in ['RGB', 'L']:
            image = image.convert('RGB')
        
        # Handle GIF animation
        if input_format.lower() == 'gif' and output_format.lower() != 'gif':
            # Extract first frame of GIF
            if hasattr(image, 'is_animated') and image.is_animated:
                image.seek(0)  # Get first frame
                image = image.convert('RGB')
        
        # Save to bytes
        output_buffer = io.BytesIO()
        
        # Special handling for different formats
        save_kwargs = {}
        if output_format.lower() in ['jpg', 'jpeg']:
            save_kwargs['quality'] = quality
            save_kwargs['optimize'] = True
        elif output_format.lower() == 'png':
            save_kwargs['optimize'] = True
            save_kwargs['compress_level'] = 6
        elif output_format.lower() == 'webp':
            save_kwargs['quality'] = quality
        
        # Handle GIF output
        if output_format.lower() == 'gif':
            if input_format.lower() == 'gif':
                # Keep as GIF
                image.save(output_buffer, format='GIF', save_all=True)
            else:
                # Convert single image to GIF
                image.save(output_buffer, format='GIF')
        else:
            # Standard save
            image.save(output_buffer, format=SUPPORTED_FORMATS[output_format.lower()][0], **save_kwargs)
        
        output_buffer.seek(0)
        return output_buffer.getvalue()
    
    except Exception as e:
        logger.error(f"Conversion error: {e}")
        return None

def get_file_extension(filename: str) -> str:
    """Extract file extension from filename"""
    return Path(filename).suffix.lower().replace('.', '')

# ==================== Bot Handlers ====================

@dp.message_handler(commands=['start'])
async def start_command(message: types.Message):
    """Handle /start command"""
    welcome_text = (
        "🎨 *Welcome to ImgPixieBot!*\n\n"
        "I can convert your images between different formats.\n"
        "📸 *Supported formats:* PNG, JPG, JPEG, WEBP, GIF, BMP, TIFF, ICO\n\n"
        "🔄 *How to use:*\n"
        "1. Send me an image\n"
        "2. Choose the format you want to convert to\n"
        "3. I'll send back the converted image!\n\n"
        "⚡ *Pro tip:* For best results, use high-quality images."
    )
    
    await message.reply(
        welcome_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=types.ReplyKeyboardRemove()
    )

@dp.message_handler(commands=['help'])
async def help_command(message: types.Message):
    """Handle /help command"""
    help_text = (
        "📖 *Help & Commands*\n\n"
        "*/start* - Welcome message and instructions\n"
        "*/help* - Show this help message\n"
        "*/formats* - Show supported formats\n"
        "*/cancel* - Cancel current operation\n\n"
        "*💡 Quick Guide:*\n"
        "1. Send any image file\n"
        "2. Choose the output format from the buttons\n"
        "3. Wait for the converted image\n\n"
        "*⚠️ Notes:*\n"
        "- Maximum file size: 20MB\n"
        "- Animated GIFs will be converted to static images\n"
        "- For JPEG output, transparent backgrounds become white"
    )
    
    await message.reply(help_text, parse_mode=ParseMode.MARKDOWN)

@dp.message_handler(commands=['formats'])
async def formats_command(message: types.Message):
    """Handle /formats command"""
    formats_text = "📋 *Supported Formats:*\n\n"
    for fmt in SUPPORTED_FORMATS.keys():
        formats_text += f"• {fmt.upper()}\n"
    
    formats_text += "\n🔄 Send an image to get started!"
    
    await message.reply(formats_text, parse_mode=ParseMode.MARKDOWN)

@dp.message_handler(commands=['cancel'])
async def cancel_command(message: types.Message):
    """Handle /cancel command"""
    user_id = message.from_user.id
    if user_id in user_states:
        del user_states[user_id]
        await message.reply("✅ Operation cancelled. You can start over anytime!")
    else:
        await message.reply("ℹ️ No active operation to cancel.")

@dp.message_handler(content_types=['photo'])
async def handle_photo(message: types.Message):
    """Handle photo messages (non-file format)"""
    user_id = message.from_user.id
    
    # Get the largest photo
    photo = message.photo[-1]
    file_info = await bot.get_file(photo.file_id)
    file_bytes = await bot.download_file(file_info.file_path)
    
    # Store in user state
    user_states[user_id] = {
        'image_bytes': file_bytes.getvalue(),
        'input_format': 'jpg'  # Telegram photos are always JPEG
    }
    
    # Show format selection
    await message.reply(
        "📸 Image received! Choose the format you want to convert to:",
        reply_markup=get_format_buttons()
    )

@dp.message_handler(content_types=['document'])
async def handle_document(message: types.Message):
    """Handle document messages (image files)"""
    user_id = message.from_user.id
    document = message.document
    
    # Check if it's an image
    ext = get_file_extension(document.file_name or '')
    if ext not in SUPPORTED_FORMATS:
        await message.reply(
            f"❌ Unsupported file format: *{ext.upper()}*\n\n"
            f"Supported formats: {', '.join([f.upper() for f in SUPPORTED_FORMATS.keys()])}",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Check file size (max 20MB)
    if document.file_size > 20 * 1024 * 1024:
        await message.reply("❌ File is too large! Maximum size: 20MB")
        return
    
    try:
        file_info = await bot.get_file(document.file_id)
        file_bytes = await bot.download_file(file_info.file_path)
        
        # Store in user state
        user_states[user_id] = {
            'image_bytes': file_bytes.getvalue(),
            'input_format': ext,
            'filename': document.file_name
        }
        
        # Show format selection
        await message.reply(
            f"✅ *{document.file_name}* received!\n"
            f"📐 Size: {document.file_size / 1024:.1f}KB\n\n"
            "Choose the output format:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_format_buttons()
        )
    except Exception as e:
        logger.error(f"Error handling document: {e}")
        await message.reply("❌ Failed to process your image. Please try again.")

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('format_'))
async def process_format_selection(callback_query: types.CallbackQuery):
    """Handle format selection callback"""
    user_id = callback_query.from_user.id
    output_format = callback_query.data.replace('format_', '')
    
    # Check if user has uploaded an image
    if user_id not in user_states:
        await callback_query.answer("❌ Please send an image first!")
        await callback_query.message.edit_text(
            "ℹ️ No image found. Please send me an image first, then select a format."
        )
        return
    
    # Get user data
    user_data = user_states[user_id]
    image_bytes = user_data['image_bytes']
    input_format = user_data['input_format']
    original_filename = user_data.get('filename', 'image')
    
    # If same format, warn user
    if input_format == output_format:
        await callback_query.answer("⚠️ Image is already in this format!", show_alert=True)
        return
    
    # Show processing status
    await callback_query.answer(f"🔄 Converting to {output_format.upper()}...")
    await callback_query.message.edit_text(
        f"🔄 Converting from *{input_format.upper()}* to *{output_format.upper()}*...\n"
        f"⏳ Please wait...",
        parse_mode=ParseMode.MARKDOWN
    )
    
    try:
        # Convert the image
        converted_bytes = await convert_image(
            image_bytes,
            input_format,
            output_format,
            quality=90
        )
        
        if not converted_bytes:
            await callback_query.message.edit_text(
                f"❌ Failed to convert image to *{output_format.upper()}*.\n"
                f"Please try again with a different format.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Determine output filename
        base_name = Path(original_filename).stem
        output_filename = f"{base_name}.{output_format}"
        
        # Send converted image
        await bot.send_document(
            chat_id=user_id,
            document=types.InputFile(
                io.BytesIO(converted_bytes),
                filename=output_filename
            ),
            caption=f"✅ Converted *{input_format.upper()}* → *{output_format.upper()}*\n"
                    f"📦 Size: {len(converted_bytes) / 1024:.1f}KB",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Clear user state
        del user_states[user_id]
        
        # Update message
        await callback_query.message.edit_text(
            f"✅ Conversion complete! Check the image I just sent you.\n\n"
            f"🔄 Send another image to convert more!"
        )
        
    except Exception as e:
        logger.error(f"Conversion error: {e}")
        await callback_query.message.edit_text(
            "❌ An error occurred during conversion. Please try again."
        )

@dp.callback_query_handler(lambda c: c.data == 'cancel')
async def cancel_callback(callback_query: types.CallbackQuery):
    """Handle cancel callback"""
    user_id = callback_query.from_user.id
    
    if user_id in user_states:
        del user_states[user_id]
        await callback_query.answer("✅ Cancelled!")
        await callback_query.message.edit_text("✅ Operation cancelled. You can start over anytime!")
    else:
        await callback_query.answer("ℹ️ No active operation.")

@dp.message_handler()
async def handle_unknown(message: types.Message):
    """Handle unknown messages"""
    await message.reply(
        "🤔 I only work with images!\n\n"
        "Send me an image or a document (PNG, JPG, WEBP, GIF, etc.)\n"
        "Or use /help to see available commands."
    )

# ==================== Main Execution ====================

if __name__ == '__main__':
    logger.info("Starting ImgPixieBot...")
    
    # Set webhook for Railway (if using webhook mode)
    # For Railway, you'd typically use webhook instead of polling
    # This example uses polling for simplicity
    
    try:
        executor.start_polling(dp, skip_updates=True)
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        raise
