"""
Module for low-level audio input-output operations.

Class summary
=============

.. autosummary::

        AudioSource
        Rewindable
        BufferAudioSource
        WaveAudioSource
        PyAudioSource
        StdinAudioSource
        PyAudioPlayer
        

Function summary
================

.. autosummary::

        from_file
        player_for
"""

from abc import ABCMeta, abstractmethod
import os
import sys
import wave

try:
    from pydub import AudioSegment

    _WITH_PYDUB = True
except ImportError:
    _WITH_PYDUB = False

__all__ = [
    "AudioIOError",
    "AudioParameterError",
    "AudioSource",
    "Rewindable",
    "BufferAudioSource",
    "WaveAudioSource",
    "PyAudioSource",
    "StdinAudioSource",
    "PyAudioPlayer",
    "from_file",
    "player_for",
]

DEFAULT_SAMPLE_RATE = 16000
DEFAULT_SAMPLE_WIDTH = 2
DEFAULT_NB_CHANNELS = 1
DATA_FORMAT = {1: "b", 2: "h", 4: "i"}


class AudioIOError(Exception):
    pass


class AudioParameterError(AudioIOError):
    pass


def check_audio_data(data, sample_width, channels):
    sample_size_bytes = int(sample_width * channels)
    nb_samples = len(data) // sample_size_bytes
    if nb_samples * sample_size_bytes != len(data):
        raise AudioParameterError(
            "The length of audio data must be an integer "
            "multiple of `sample_width * channels`"
        )


def _guess_audio_format(fmt, filename):
    if fmt is None:
        extension = os.path.splitext(filename.lower())[1][1:]
        return extension if extension else None
    return fmt.lower()


def _normalize_use_channel(use_channel):
    """
    Returns a value of `use_channel` as expected by audio read/write fuctions.
    If `use_channel` is `None`, returns 0. If it's an integer, or the special
    str 'mix' returns it as is. If it's `left` or `right` returns 0 or 1
    respectively.
    """
    if use_channel is None:
        return 0
    if use_channel == "mix" or isinstance(use_channel, int):
        return use_channel
    try:
        return ["left", "right"].index(use_channel)
    except ValueError:
        err_message = "'use_channel' parameter must be an integer "
        "or one of ('left', 'right', 'mix'), found: '{}'".format(use_channel)
        raise AudioParameterError(err_message)


def _get_audio_parameters(param_dict):
    """
    Gets audio parameters from a dictionary of parameters.
    A parameter can have a long name or a short name. If the long name is
    present, the short name is ignored. In neither is present then
    `AudioParameterError` is raised  except for the `use_channel` (or `uc`)
    parameter for which a defalut value of 0 is returned.

    Also raises `AudioParameterError` if sampling rate, sample width or
    channels is not an integer.

    Expected parameters are:

        `sampling_rate`, `sr`: int, sampling rate.
        `sample_width`, `sw`: int, sample size in bytes.
        `channels`, `ch`: int, number of channels.
        `use_channel`, `us`: int or str, which channel to use from data.
            Default value is 0 (first channel). The following special str
            values are also accepted:
                `left`: alias for 0
                `right`: alias for 1
                `mix`: indicates that all channels should be mixed up into one
                    single channel

    :Returns

        param_dict: tuple
            audio parameters as a tuple (sampling_rate,
                                         sample_width,
                                         channels,
                                         use_channel)
    """
    err_message = "'{ln}' (or '{sn}') must be an integer, found: '{val}'"
    parameters = []
    for (long_name, short_name) in (
        ("sampling_rate", "sr"),
        ("sample_width", "sw"),
        ("channels", "ch"),
    ):
        param = param_dict.get(long_name, None) or param_dict.get(
            short_name, None
        )
        if param is None or not isinstance(param, int):
            raise AudioParameterError(
                err_message.format(ln=long_name, sn=short_name, val=param)
            )
        parameters.append(param)
    use_channel = param_dict.get("use_channel", param_dict.get("uc", 0))
    return tuple(parameters) + (_normalize_use_channel(use_channel),)


class AudioSource:
    """ 
    Base class for audio source objects.

    Subclasses should implement methods to open/close and audio stream 
    and read the desired amount of audio samples.

    :Parameters:

        `sampling_rate` : int
            Number of samples per second of audio stream. Default = 16000.

        `sample_width` : int
            Size in bytes of one audio sample. Possible values : 1, 2, 4.
            Default = 2.

        `channels` : int
            Number of channels of audio stream. The current version supports
            only mono audio streams (i.e. one channel).
    """

    __metaclass__ = ABCMeta

    def __init__(
        self,
        sampling_rate=DEFAULT_SAMPLE_RATE,
        sample_width=DEFAULT_SAMPLE_WIDTH,
        channels=DEFAULT_NB_CHANNELS,
    ):

        if sample_width not in (1, 2, 4):
            raise AudioParameterError(
                "Sample width must be one of: 1, 2 or 4 (bytes)"
            )

        if channels != 1:
            raise AudioParameterError("Only mono audio is currently supported")

        self._sampling_rate = sampling_rate
        self._sample_width = sample_width
        self._channels = channels

    @abstractmethod
    def is_open(self):
        """ Return True if audio source is open, False otherwise """

    @abstractmethod
    def open(self):
        """ Open audio source """

    @abstractmethod
    def close(self):
        """ Close audio source """

    @abstractmethod
    def read(self, size):
        """
        Read and return `size` audio samples at most.

        :Parameters:

            `size` : int
                the number of samples to read.

        :Returns:

            Audio data as a string of length 'N' * 'sample_width' * 'channels', where 'N' is:

            - `size` if `size` < 'left_samples'

            - 'left_samples' if `size` > 'left_samples' 
        """

    def get_sampling_rate(self):
        """ Return the number of samples per second of audio stream """
        return self.sampling_rate

    @property
    def sampling_rate(self):
        """ Number of samples per second of audio stream """
        return self._sampling_rate

    @property
    def sr(self):
        """ Number of samples per second of audio stream """
        return self._sampling_rate

    def get_sample_width(self):
        """ Return the number of bytes used to represent one audio sample """
        return self.sample_width

    @property
    def sample_width(self):
        """ Number of bytes used to represent one audio sample """
        return self._sample_width

    @property
    def sw(self):
        """ Number of bytes used to represent one audio sample """
        return self._sample_width

    def get_channels(self):
        """ Return the number of channels of this audio source """
        return self.channels

    @property
    def channels(self):
        """ Number of channels of this audio source """
        return self._channels

    @property
    def ch(self):
        """ Return the number of channels of this audio source """
        return self.channels


class Rewindable:
    """
    Base class for rewindable audio streams.
    Subclasses should implement methods to return to the beginning of an
    audio stream as well as method to move to an absolute audio position
    expressed in time or in number of samples. 
    """

    __metaclass__ = ABCMeta

    @abstractmethod
    def rewind(self):
        """ Go back to the beginning of audio stream """
        pass

    @abstractmethod
    def get_position(self):
        """ Return the total number of already read samples """

    @abstractmethod
    def get_time_position(self):
        """ Return the total duration in seconds of already read data """

    @abstractmethod
    def set_position(self, position):
        """ Move to an absolute position 

        :Parameters:

            `position` : int
                number of samples to skip from the start of the stream
        """

    @abstractmethod
    def set_time_position(self, time_position):
        """ Move to an absolute position expressed in seconds

        :Parameters:

            `time_position` : float
                seconds to skip from the start of the stream
        """
        pass


class BufferAudioSource(AudioSource, Rewindable):
    """
    An :class:`AudioSource` that encapsulates and reads data from a memory buffer.
    It implements methods from :class:`Rewindable` and is therefore a navigable :class:`AudioSource`.
    """

    def __init__(
        self,
        data_buffer,
        sampling_rate=DEFAULT_SAMPLE_RATE,
        sample_width=DEFAULT_SAMPLE_WIDTH,
        channels=DEFAULT_NB_CHANNELS,
    ):
        AudioSource.__init__(self, sampling_rate, sample_width, channels)
        check_audio_data(data_buffer, sample_width, channels)
        self._buffer = data_buffer
        self._sample_size_all_channels = sample_width * channels
        self._current_position_bytes = 0
        self._is_open = False

    def is_open(self):
        return self._is_open

    def open(self):
        self._is_open = True

    def close(self):
        self._is_open = False
        self.rewind()

    def read(self, size):
        if not self._is_open:
            raise AudioIOError("Stream is not open")
        bytes_to_read = self._sample_size_all_channels * size
        data = self._buffer[
            self._current_position_bytes : self._current_position_bytes
            + bytes_to_read
        ]
        if data:
            self._current_position_bytes += len(data)
            return data
        return None

    def get_data_buffer(self):
        """ Return all audio data as one string buffer. """
        return self._buffer

    def set_data(self, data_buffer):
        """ Set new data for this audio stream. 

        :Parameters:

            `data_buffer` : str, basestring, Bytes
                a string buffer with a length multiple of (sample_width * channels)
        """
        check_audio_data(data_buffer, self.sample_width, self.channels)
        self._buffer = data_buffer
        self._current_position_bytes = 0

    def append_data(self, data_buffer):
        """ Append data to this audio stream

        :Parameters:

            `data_buffer` : str, basestring, Bytes
                a buffer with a length multiple of (sample_width * channels)
        """
        check_audio_data(data_buffer, self.sample_width, self.channels)
        self._buffer += data_buffer

    def rewind(self):
        self.set_position(0)

    def get_position(self):
        return self._current_position_bytes / self._sample_size_all_channels

    def get_time_position(self):
        return float(self._current_position_bytes) / (
            self._sample_size_all_channels * self.sampling_rate
        )

    def set_position(self, position):
        if position < 0:
            raise ValueError("position must be >= 0")
        position *= self._sample_size_all_channels
        self._current_position_bytes = (
            position if position < len(self._buffer) else len(self._buffer)
        )

    def set_time_position(self, time_position):  # time in seconds
        position = int(self.sampling_rate * time_position)
        self.set_position(position)


class WaveAudioSource(AudioSource):
    """
    A class for an `AudioSource` that reads data from a wave file.

    :Parameters:

        `filename` :
            path to a valid wave file
    """

    def __init__(self, filename):

        self._filename = filename
        self._audio_stream = None

        stream = wave.open(self._filename)
        AudioSource.__init__(
            self,
            stream.getframerate(),
            stream.getsampwidth(),
            stream.getnchannels(),
        )
        stream.close()

    def is_open(self):
        return self._audio_stream is not None

    def open(self):
        if self._audio_stream is None:
            self._audio_stream = wave.open(self._filename)

    def close(self):
        if self._audio_stream is not None:
            self._audio_stream.close()
            self._audio_stream = None

    def read(self, size):
        if self._audio_stream is None:
            raise IOError("Stream is not open")
        else:
            data = self._audio_stream.readframes(size)
            if data is None or len(data) < 1:
                return None
            return data


class PyAudioSource(AudioSource):
    """
    A class for an `AudioSource` that reads data the built-in microphone using PyAudio. 
    """

    def __init__(
        self,
        sampling_rate=DEFAULT_SAMPLE_RATE,
        sample_width=DEFAULT_SAMPLE_WIDTH,
        channels=DEFAULT_NB_CHANNELS,
        frames_per_buffer=1024,
        input_device_index=None,
    ):

        AudioSource.__init__(self, sampling_rate, sample_width, channels)
        self._chunk_size = frames_per_buffer
        self.input_device_index = input_device_index

        import pyaudio

        self._pyaudio_object = pyaudio.PyAudio()
        self._pyaudio_format = self._pyaudio_object.get_format_from_width(
            self.sample_width
        )
        self._audio_stream = None

    def is_open(self):
        return self._audio_stream is not None

    def open(self):
        self._audio_stream = self._pyaudio_object.open(
            format=self._pyaudio_format,
            channels=self.channels,
            rate=self.sampling_rate,
            input=True,
            output=False,
            input_device_index=self.input_device_index,
            frames_per_buffer=self._chunk_size,
        )

    def close(self):
        if self._audio_stream is not None:
            self._audio_stream.stop_stream()
            self._audio_stream.close()
            self._audio_stream = None

    def read(self, size):
        if self._audio_stream is None:
            raise IOError("Stream is not open")

        if self._audio_stream.is_active():
            data = self._audio_stream.read(size)
            if data is None or len(data) < 1:
                return None
            return data

        return None


class StdinAudioSource(AudioSource):
    """
    A class for an :class:`AudioSource` that reads data from standard input.
    """

    def __init__(
        self,
        sampling_rate=DEFAULT_SAMPLE_RATE,
        sample_width=DEFAULT_SAMPLE_WIDTH,
        channels=DEFAULT_NB_CHANNELS,
    ):

        AudioSource.__init__(self, sampling_rate, sample_width, channels)
        self._is_open = False

    def is_open(self):
        return self._is_open

    def open(self):
        self._is_open = True

    def close(self):
        self._is_open = False

    def read(self, size):
        if not self._is_open:
            raise IOError("Stream is not open")

        to_read = size * self.sample_width * self.channels
        if sys.version_info >= (3, 0):
            data = sys.stdin.buffer.read(to_read)
        else:
            data = sys.stdin.read(to_read)

        if data is None or len(data) < 1:
            return None

        return data


class PyAudioPlayer:
    """
    A class for audio playback using Pyaudio
    """

    def __init__(
        self,
        sampling_rate=DEFAULT_SAMPLE_RATE,
        sample_width=DEFAULT_SAMPLE_WIDTH,
        channels=DEFAULT_NB_CHANNELS,
    ):
        if not sample_width in (1, 2, 4):
            raise ValueError("Sample width must be one of: 1, 2 or 4 (bytes)")

        self.sampling_rate = sampling_rate
        self.sample_width = sample_width
        self.channels = channels

        import pyaudio

        self._p = pyaudio.PyAudio()
        self.stream = self._p.open(
            format=self._p.get_format_from_width(self.sample_width),
            channels=self.channels,
            rate=self.sampling_rate,
            input=False,
            output=True,
        )

    def play(self, data):
        if self.stream.is_stopped():
            self.stream.start_stream()

        for chunk in self._chunk_data(data):
            self.stream.write(chunk)

        self.stream.stop_stream()

    def stop(self):
        if not self.stream.is_stopped():
            self.stream.stop_stream()
        self.stream.close()
        self._p.terminate()

    def _chunk_data(self, data):
        # make audio chunks of 100 ms to allow interruption (like ctrl+c)
        chunk_size = int(
            (self.sampling_rate * self.sample_width * self.channels) / 10
        )
        start = 0
        while start < len(data):
            yield data[start : start + chunk_size]
            start += chunk_size


def player_for(audio_source):
    """
    Return a :class:`PyAudioPlayer` that can play data from `audio_source`.

    :Parameters:

        `audio_source` : 
            an `AudioSource` object.

    :Returns:

        `PyAudioPlayer` that has the same sampling rate, sample width and number of channels
        as `audio_source`.
    """

    return PyAudioPlayer(
        audio_source.get_sampling_rate(),
        audio_source.get_sample_width(),
        audio_source.get_channels(),
    )


def _load_raw(
    file,
    sampling_rate,
    sample_width,
    channels,
    use_channel=0,
    large_file=False,
):
    """
    Load a raw audio file with standard Python.
    If `large_file` is True, audio data will be lazily
    loaded to memory.

    See also :func:`from_file`.

    :Parameters:
        `file` : filelike object or str
            raw audio file to open
        `sampling_rate`: int
            sampling rate of audio data
        `sample_width`: int
            sample width of audio data
        `channels`: int
            number of channels of audio data
        `use_channel`: int
            audio channel to read if file is not mono audio. This must be an integer
            0 >= and < channels, or one of 'left' (treated as 0 or first channel), or
            right (treated as 1 or second channels). 

    :Returns:

        `PyAudioPlayer` that has the same sampling rate, sample width and number of channels
        as `audio_source`.
    """
    if None in (sampling_rate, sample_width, channels):
        raise AudioParameterError(
            "All audio parameters are required for raw audio files"
        )

    if large_file:
        return RawAudioSource(
            file,
            sampling_rate=sampling_rate,
            sample_width=sample_width,
            channels=channels,
            use_channel=use_channel,
        )
    else:
        with open(file, "rb") as fp:
            data = fp.read()
        if channels != 1:
            # TODO check if striding with mmap doesn't load all data to memory
            data = _extract_selected_channel(
                data, channels, sample_width, use_channel
            )
        return BufferAudioSource(
            data,
            sampling_rate=sampling_rate,
            sample_width=sample_width,
            channels=1,
        )


def _load_wave(filename, large_file=False, use_channel=0):
    """
    Load a wave audio file with standard Python.
    If `large_file` is True, audio data will be lazily
    loaded to memory.

    See also :func:`to_file`.
    """
    if large_file:
        return WaveAudioSource(filename, use_channel)
    with wave.open(filename) as fp:
        channels = fp.getnchannels()
        srate = fp.getframerate()
        swidth = fp.getsampwidth()
        data = fp.readframes(-1)
    if channels > 1:
        data = _extract_selected_channel(data, channels, swidth, use_channel)
    return BufferAudioSource(
        data, sampling_rate=srate, sample_width=swidth, channels=1
    )


def _load_with_pydub(filename, audio_format, use_channel=0):
    """Open compressed audio file using pydub. If a video file
    is passed, its audio track(s) are extracted and loaded.
    This function should not be called directely, use :func:`from_file`
    instead.

    :Parameters:

    `filename`:
        path to audio file.
    `audio_format`:
        string, audio file format (e.g. raw, webm, wav, ogg)
    """
    func_dict = {
        "mp3": AudioSegment.from_mp3,
        "ogg": AudioSegment.from_ogg,
        "flv": AudioSegment.from_flv,
    }
    open_function = func_dict.get(audio_format, AudioSegment.from_file)
    segment = open_function(filename)
    data = segment._data
    if segment.channels > 1:
        data = _extract_selected_channel(
            data, segment.channels, segment.sample_width, use_channel
        )
    return BufferAudioSource(
        data_buffer=data,
        sampling_rate=segment.frame_rate,
        sample_width=segment.sample_width,
        channels=1,
    )


def from_file(filename):
    """
    Create an `AudioSource` object using the audio file specified by `filename`.
    The appropriate :class:`AudioSource` class is guessed from file's extension.

    :Parameters:

        `filename` :
            path to an audio file.

    :Returns:

        an `AudioSource` object that reads data from the given file.
    """

    if filename.lower().endswith(".wav"):
        return WaveAudioSource(filename)

    raise Exception(
        "Can not create an AudioSource object from '%s'" % (filename)
    )


def _save_raw(file, data):
    """
    Saves audio data as a headerless (i.e. raw) file.
    See also :func:`to_file`.
    """
    with open(file, "wb") as fp:
        fp.write(data)


def _save_wave(file, data, sampling_rate, sample_width, channels):
    """
    Saves audio data to a wave file.
    See also :func:`to_file`.
    """
    # use standard python's wave module
    with wave.open(file, "w") as fp:
        fp.setframerate(sampling_rate)
        fp.setsampwidth(sample_width)
        fp.setnchannels(channels)
        fp.writeframes(data)


def _save_with_pydub(
    file, data, audio_format, sampling_rate, sample_width, channels
):
    """
    Saves audio data with pydub (https://github.com/jiaaro/pydub).
    See also :func:`to_file`.
    """
    segment = AudioSegment(
        data,
        frame_rate=sampling_rate,
        sample_width=sample_width,
        channels=channels,
    )
    with open(file, "wb") as fp:
        segment.export(fp, format=audio_format)


def to_file(data, file, audio_format=None, **kwargs):
    """
    Writes audio data to file. If `audio_format` is `None`, output
    audio format will be guessed from extension. If `audio_format`
    is `None` and `file` comes without an extension then audio
    data will be written as a raw audio file.

    :Parameters:

        `data`: buffer of bytes
            audio data to be written. Can be a `bytes`, `bytearray`,
            `memoryview`, `array` or `numpy.ndarray` object.
        `file`: str
            path to output audio file
        `audio_format`: str
            audio format used to save data (e.g. raw, webm, wav, ogg)
        :kwargs:
            If an audio format other than raw is used, the following
            keyword arguments are required:
            `sampling_rate`, `sr`: int
                sampling rate of audio data
            `sample_width`, `sw`: int
                sample width (i.e., number of bytes of one audio sample)
            `channels`, `ch`: int
                number of channels of audio data
    :Raises:

        `AudioParameterError` if output format is different than raw and one
        or more audio parameters are missing.
        `AudioIOError` if audio data cannot be written in the desired format.
    """
    audio_format = _guess_audio_format(audio_format, file)
    if audio_format in (None, "raw"):
        _save_raw(file, data)
        return
    try:
        params = _get_audio_parameters(kwargs)
        sampling_rate, sample_width, channels, _ = params
    except AudioParameterError as exc:
        err_message = "All audio parameters are required to save formats "
        "other than raw. Error detail: {}".format(exc)
        raise AudioParameterError(err_message)
    if audio_format in ("wav", "wave"):
        _save_wave(file, data, sampling_rate, sample_width, channels)
    elif _WITH_PYDUB:
        _save_with_pydub(
            file, data, audio_format, sampling_rate, sample_width, channels
        )
    else:
        err_message = "cannot write file format {} (file name: {})"
        raise AudioIOError(err_message.format(audio_format, file))
