"""Progress photos: re-encoded on upload, served only to their owner."""
import io

from django import forms
from django.core.files.base import ContentFile
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError

from .models import ProgressPhoto

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_SIDE = 2000
JPEG_QUALITY = 85
POSES = [pose for pose, _ in ProgressPhoto.Pose.choices]


def reencode(upload):
    """Turns the upload into a fresh JPEG.

    Re-encoding drops all metadata, including the GPS position phones write into
    their photos, and keeps files at a sensible size.
    """
    if upload.size > MAX_UPLOAD_BYTES:
        raise forms.ValidationError('Das Bild ist zu groß (höchstens 15 MB).')
    try:
        with Image.open(upload) as image:
            image = ImageOps.exif_transpose(image)
            image = image.convert('RGB')
            image.thumbnail((MAX_SIDE, MAX_SIDE))
            output = io.BytesIO()
            image.save(output, 'JPEG', quality=JPEG_QUALITY, optimize=True)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise forms.ValidationError('Diese Datei ist kein lesbares Bild.')
    return ContentFile(output.getvalue(), name='photo.jpg')


class PhotoUploadForm(forms.Form):
    date = forms.DateField(label='Datum', widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    vorne = forms.FileField(label='Vorne', required=False)
    seite = forms.FileField(label='Seite', required=False)
    hinten = forms.FileField(label='Hinten', required=False)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.initial.setdefault('date', timezone.localdate())
        for pose in POSES:
            self.fields[pose].widget.attrs.update({'accept': 'image/*'})

    def clean_date(self):
        day = self.cleaned_data['date']
        if day > timezone.localdate():
            raise forms.ValidationError('Das Datum darf nicht in der Zukunft liegen.')
        return day

    def clean(self):
        cleaned = super().clean()
        uploads = {pose: cleaned.get(pose) for pose in POSES if cleaned.get(pose)}
        if not uploads and not self.errors:
            raise forms.ValidationError('Bitte wähle mindestens ein Foto aus.')
        for pose, upload in uploads.items():
            try:
                cleaned[pose] = reencode(upload)
            except forms.ValidationError as error:
                self.add_error(pose, error)
        return cleaned

    def save(self):
        """One photo per day and pose: a new upload replaces the old one."""
        saved = []
        for pose in POSES:
            content = self.cleaned_data.get(pose)
            if not content:
                continue
            photo, _ = ProgressPhoto.objects.get_or_create(
                user=self.user, date=self.cleaned_data['date'], pose=pose,
                defaults={'image': ''},
            )
            if photo.image:
                photo.image.delete(save=False)
            photo.image.save('photo.jpg', content, save=True)
            saved.append(photo)
        return saved


def delete_photo_files(photos):
    for photo in photos:
        if photo.image:
            photo.image.delete(save=False)
