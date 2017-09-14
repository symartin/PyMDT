import io
import os
from struct import *

from MDTdeclaration import *


class MDTFile:

    class _MDTBufferedReaderDecorator(object):
        def __init__(self, file_):
            self._file = file_

        def shift_stream_position(self, shift_bytes):
            self._file.seek(shift_bytes, io.SEEK_CUR)

        def read_uint16(self):
            return unpack("<H", self._file.read(2))[0]

        def read_uint32(self):
            return unpack("<I", self._file.read(4))[0]

        def read_char(self):
            return unpack("<c", self._file.read(1))[0]

        def read_uchar(self):
            return int(unpack('<B', self._file.read(1))[0])

        def __getattr__(self, attr):
            return getattr(self._file, attr)

    def __init__(self):
        self.size       = 0
        self.last_frame = 0
        self.frames     = []
        self._file      =""

    def load_mdt_file(self, file):
        try:
            if isinstance(file, str):
                self._file = self._MDTBufferedReaderDecorator(open(file, mode='rb'))
            else:
                self._file = self._MDTBufferedReaderDecorator(file)

            mdt_file.read_header(self._file)

            for i in range(mdt_file.last_frame + 1):
                frame = MDTFrame()
                frame.read_header(self._file)
                frame.print_header()


                if frame.type == MDTFrameType.MDT_FRAME_SCANNED:
                    pass

                elif (frame.type == MDTFrameType.MDT_FRAME_SPECTROSCOPY or
                              frame.type == MDTFrameType.MDT_FRAME_CURVES):
                    pass

                elif frame.type == MDTFrameType.MDT_FRAME_TEXT:
                    frame.read_text_frame(self._file)
                    #frame.print_header()

                elif frame.type == MDTFrameType.MDT_FRAME_OLD_MDA:
                    pass

                elif frame.type == MDTFrameType.MDT_FRAME_MDA:
                    pass

                elif frame.type == MDTFrameType.MDT_FRAME_CURVES_NEW:
                    pass

                elif frame.type == MDTFrameType.MDT_FRAME_PALETTE:
                    pass

                else:
                    pass

                self.frames.append(frame)

                # to be sure we reposition the pointer where it should be after reading the frame
                self._file.seek(frame.fstart + frame.size)


        finally:
            self._file.close()


    def print_me(self):
        print ("file size w/o header: " + str(self.size) + " bits")
        print("Last frame: " + str(self.last_frame))

    def read_header(self, file):
        if file_size < 34: raise Exception("The file is shorter than it's header size")
        # magic header
        file.shift_stream_position(4)

        # File size (w/o header)
        self.size = file.read_uint32()

        #  4 bytes reserved (??)
        file.shift_stream_position(4)

        # last frame
        self.last_frame = file.read_uint16()

        #  18 bytes reserved (??)
        file.shift_stream_position(18)

        # documentation specifies 32 bytes long header, but zeroth frame
        # starts at 33th byte in reality
        file.shift_stream_position(1)

        self.print_me()

        if file_size < self.size + 33:
            raise Exception("Mismatch between the actual file size \
                             and the size declared in the header")

class MDTFrame:

    def __init__(self):
     self.size       = 0
     self.type       = None
     self.version    = (0,0)
     self.year       = 0
     self.month      = 0
     self.day        = 0
     self.hour       = 0
     self.min        = 0
     self.sec        = 0
     self.fstart     = 0
     self.var_size   = 0 # v6 and older only */
     self.data       = None
     self.metadata   = ""
     self.title      = ""

    def read_header(self, file):
        """
        load the header of the frame, starting at 'file' current position.
        :param file: a MDTBufferedReaderDecorator object warping the mdt file to load
        """
        self.fstart = file.tell()

        # the size of the frame with header
        self.size = file.read_uint32()

        # frame type
        self.type = file.read_uint16()


        # frame version, on the C code, there is :
        # frame->version = ((guint)p[0] << 8) + (gsize)p[1];
        # debug("Frame #%u version: %d.%d",
        #          i, frame->version/0x100, frame->version % 0x100);
        # that is not clear for me ...
        self.version = (int((int.from_bytes(file.read_char(), byteorder='little') << 8) / 256),
                          int.from_bytes(file.read_char(), byteorder='little') % 256)

        # datetime
        self.year  = file.read_uint16()
        self.month = file.read_uint16()
        self.day   = file.read_uint16()
        self.hour  = file.read_uint16()
        self.min   = file.read_uint16()
        self.sec   = file.read_uint16()

        # unsigned integer, size of variables (in version 6 and earlier). Not used in version 7.
        self.var_size = file.read_uint16()

    def read_text_frame(self,file):
        """
        Read the title, data et xml metadata of a text frame, starting at the file current position

        I reverse engineered the format, so I clearly not sure of what I'have done :)
        basically the text frame is composed of two parts, the text (the text entered by the user)
        and the XML metadata part.

        In the text part
         - 2 byte for the text length
                Note : apparently if the text frame has more than 65535 characters, Nova-PX can write it
                in this case the length is at least on 3 bytes, but it cannot reopen it...
         - 16 0x00 bytes
         - the text encoded on 1 byte (at least for latin characters)
         - 1 byte the length of the title then 3 0x00,
                if  the title is the default one 'Text Frame' this byte is not there
                and there are only the 3 0x00
                if the title is empty (i.e. "") there is 4 0x00 before the metadata
                Note : I don't know what append if the title is mor than 256 long, so don't do that !
         - the title

        In the xml part
         - the first 2 bytes are the size of this part usually 580
         - two 0x00 byte
         - the XML text : the characters are utf-16 packed by 2 bytes

        After that, there are some non-zero bytes, but I don't know what there are for.
        """
        size = self.size - ByteSize.FRAME_HEADER_SIZE
        # print(file.read(size))
        # shift_stream_position(file, -size)

        if size < 1:
            raise Exception("the frame size is smaller than the frame header size")

        data_len = file.read_uint16() # unpack('<H', file.read(2))[0]  # int(data_buffer[pos])

        if size < 18 + data_len + 4:  # +4 for the title length bytes and the 3 zeros
            raise Exception("the frame size is smaller than the data size")

        # we jump the 16 0x00 bytes
        file.shift_stream_position(16)

        # the main text
        self.data = file.read(data_len).decode('utf-8')

        # is there a title to this frame
        title_len = file.read_uchar()
        title_trail = unpack('<3B', file.read(3)) #TODO : do something nicer with the function peak()

        # the default title and not an empty title.
        if title_len == 0 and sum(title_trail) != 0:
            title_len = 11
        elif title_trail == 0:  # the title is empty
            file.shift_stream_position(-1)

        if size < 18 + data_len + 4 + title_len:
            raise Exception("the frame size is smaller than the data size + title size")

        # the title of the frame
        self.title = file.read(title_len).decode('utf-8')

        if size < 18 + data_len + 4 + title_len + 2:
            raise Exception("the frame size is smaller than the data size + title size + XML header")

        # we unpack the length of the metadata on 2 bytes (unit16)
        xml_len = file.read_uint16()

        if size < 18 + data_len + 4 + title_len + 2 + xml_len:
            raise Exception("the frame size is smaller than the data size + title size + XML data")

        # we jump the 2 0x00 byte
        file.shift_stream_position(2)

        # the characters are packed on 2 bytes (it's UTF-16)
        self.metadata = file.read(xml_len).decode('utf-16')

    def read_mda_frame(self,file):
        pass

    def print_header(self):
        """
        Print all the info load from the frame header
        (for debug purpose).
        """
        print("--------------------------------------")
        print("Frame start at byte %d" % self.fstart)
        print("frame size: " + str(self.size) + " bytes")
        print("Frame version: " + str(self.version))
        print("Frame datetime: %d-%02d-%02d %02d:%02d:%02d" % \
               (self.year, self.month, self.day, self.hour, self.min, self.sec))
        print("frame var_size : " + str(self.var_size) + " -- Not use in version 7.x")
        print("Frame type : " + str(self.type) + " -- "+ str(MDTFrameType(self.type)))
        print("--------------------------------------")





path = "/Users/sylvainmartin/Documents/Work/Projets/python/nt-mdt/"
filename = path + "test5.mdt"
mdt_file = MDTFile()


# def shift_stream_position(file_, shift_bytes):
#     file_.seek(shift_bytes, io.SEEK_CUR)
#
# def read_uint16 (f):
#     #int.from_bytes
#     return unpack("<H", f.read(2))[0]
#
# def read_uint32(f):
#     return unpack("<I", f.read(4))[0]
#
# def read_char(f):
#     return unpack("<c", f.read(1))[0]

file_size = os.path.getsize(filename)

if __name__ == "__main__":
#with open(filename, mode='rb') as file_:  # b is important -> binary
    #file = MDTBufferedReaderDecorator(file_)
    #print(type(file))

    mdt_file.load_mdt_file(filename)




    # for i in  range(mdt_file.last_frame+1) :
    #     frame = MDTFrame()
    #     frame.read_header(file)
    #     #frame.print_header()
    #
    #
    #     if frame.type == MDTFrameType.MDT_FRAME_SCANNED :
    #
    #         pass
    #     elif (frame.type == MDTFrameType.MDT_FRAME_SPECTROSCOPY or
    #         frame.type == MDTFrameType.MDT_FRAME_CURVES):
    #
    #         pass
    #     elif frame.type == MDTFrameType.MDT_FRAME_TEXT :
    #         frame.read_text_frame(file)
    #         frame.print_header()
    #
    #     elif frame.type == MDTFrameType.MDT_FRAME_OLD_MDA:
    #
    #         pass
    #     elif frame.type == MDTFrameType.MDT_FRAME_MDA:
    #
    #         pass
    #     elif frame.type == MDTFrameType.MDT_FRAME_CURVES_NEW:
    #
    #         pass
    #     elif frame.type == MDTFrameType.MDT_FRAME_PALETTE:
    #
    #         pass
    #     else :
    #         pass
    #
    #     file.seek(frame.fstart + frame.size)
    #     mdt_file.frames.append(frame)





"""static gboolean
mdt_real_load(const guchar *buffer,
              guint size,
              MDTFile *mdtfile,
              GError **error)
{
   
 @   p = buffer + 4;  /* magic header */
  @  mdtfile->size = gwy_get_guint32_le(&p);
  @  gwy_debug("File size (w/o header): %u", mdtfile->size);
  @  p += 4;  /* reserved */
    mdtfile->last_frame = gwy_get_guint16_le(&p);
    gwy_debug("Last frame: %u", mdtfile->last_frame);
    p += 18;  /* reserved */
    /* XXX: documentation specifies 32 bytes long header, but zeroth frame
     * starts at 33th byte in reality */
    p++;

    if (err_SIZE_MISMATCH(error, size, mdtfile->size + 33, TRUE))
        return FALSE;

    /* Frames */
    mdtfile->frames = g_new0(MDTFrame, mdtfile->last_frame + 1);
    for (i = 0; i <= mdtfile->last_frame; i++) {
        MDTFrame *frame = mdtfile->frames + i;

        fstart = p;
        if ((guint)(p - buffer) + FRAME_HEADER_SIZE > size) {
            g_set_error(error, GWY_MODULE_FILE_ERROR,
                        GWY_MODULE_FILE_ERROR_DATA,
                        _("End of file reached in frame header #%u."), i);
            return FALSE;
        }
        frame->size = gwy_get_guint32_le(&p);
        gwy_debug("Frame #%u size: %u", i, frame->size);
        if ((guint)(p - buffer) + frame->size - 4 > size) {
            g_set_error(error, GWY_MODULE_FILE_ERROR,
                        GWY_MODULE_FILE_ERROR_DATA,
                        _("End of file reached in frame data #%u."), i);
            return FALSE;
        }
        frame->type = gwy_get_guint16_le(&p);
#ifdef DEBUG
        gwy_debug("Frame #%u type: %s", i,
                  gwy_enum_to_string(frame->type,
                                     frame_types, G_N_ELEMENTS(frame_types)));
#endif
        frame->version = ((guint)p[0] << 8) + (gsize)p[1];
        p += 2;
        gwy_debug("Frame #%u version: %d.%d",
                  i, frame->version/0x100, frame->version % 0x100);
        frame->year = gwy_get_guint16_le(&p);
        frame->month = gwy_get_guint16_le(&p);
        frame->day = gwy_get_guint16_le(&p);
        frame->hour = gwy_get_guint16_le(&p);
        frame->min = gwy_get_guint16_le(&p);
        frame->sec = gwy_get_guint16_le(&p);
        gwy_debug("Frame #%u datetime: %d-%02d-%02d %02d:%02d:%02d",
                  i, frame->year, frame->month, frame->day,
                  frame->hour, frame->min, frame->sec);
        frame->var_size = gwy_get_guint16_le(&p);
        gwy_debug("Frame #%u var size: %u", i, frame->var_size);
        if (err_SIZE_MISMATCH(error, frame->var_size + FRAME_HEADER_SIZE,
                              frame->size, FALSE))
            return FALSE;

        switch (frame->type) {
            case MDT_FRAME_SCANNED:
            if (frame->var_size < AXIS_SCALES_SIZE) {
                g_set_error(error, GWY_MODULE_FILE_ERROR,
                            GWY_MODULE_FILE_ERROR_DATA,
                            _("Frame #%u is too short for "
                              "scanned data header."), i);
                return FALSE;
            }

            scannedframe = g_new0(MDTScannedDataFrame, 1);
            if (!mdt_scanned_data_vars(p, fstart, scannedframe,
                                       frame->size, frame->var_size, error))
                return FALSE;
            frame->frame_data = scannedframe;
            break;

            case MDT_FRAME_SPECTROSCOPY:
            case MDT_FRAME_CURVES:
            if (frame->var_size < AXIS_SCALES_SIZE) {
                g_set_error(error, GWY_MODULE_FILE_ERROR,
                            GWY_MODULE_FILE_ERROR_DATA,
                            _("Frame #%u is too short for "
                              "spectroscopy data header."), i);
                return FALSE;
            }

            spframe = g_new0(MDTSpectroscopyDataFrame, 1);
            spframe->frame_type = frame->type;
            if (!mdt_spectroscopy_data_vars(p, fstart, spframe,
                                       frame->size, frame->var_size, error))
                return FALSE;
            frame->frame_data = spframe;
            break;

            case MDT_FRAME_TEXT:
            gwy_debug("Cannot read text frame");
            /*
            p = fstart + FRAME_HEADER_SIZE + frame->var_size;
            p += 16;
            for (j = 0; j < frame->size - (p - fstart); j++)
                g_print("%c", g_ascii_isprint(p[j]) ? p[j] : '.');
            g_printerr("%s\n", g_convert(p, frame->size - (p - fstart),
                                         "UCS-2", "UTF-8", NULL, &j, NULL));
                                         */
            break;

            case MDT_FRAME_OLD_MDA:
            gwy_debug("Cannot read old MDA frame");
            break;

            case MDT_FRAME_MDA:
            mdaframe = g_new0(MDTMDAFrame, 1);
            if (!mdt_mda_vars(p, fstart, mdaframe,
                              frame->size, frame->var_size, error))
                return FALSE;
            frame->frame_data = mdaframe;
            break;

            case MDT_FRAME_CURVES_NEW:
            newSpecFrame = g_new0(MDTNewSpecFrame, 1);
            newSpecFrame->rFrameName = NULL;

            newSpecFrame->blocks = NULL;
            newSpecFrame->blockCount = 0;
            newSpecFrame->pointInfo = NULL;
            newSpecFrame->pointCount = 0;
            newSpecFrame->dataInfo = NULL;
            newSpecFrame->dataCount = 0;
            newSpecFrame->measInfo = NULL;
            newSpecFrame->measCount = 0;
            newSpecFrame->axisInfo = NULL;
            newSpecFrame->axisCount = 0;
            newSpecFrame->nameInfo = NULL;
            newSpecFrame->nameCount = 0;

            if (!mdt_newspec_data_vars(p, fstart, newSpecFrame,
                                       frame->size, frame->var_size,
                                       error))
                return FALSE;
            frame->frame_data = newSpecFrame;
            break;

            case MDT_FRAME_PALETTE:
            gwy_debug("Cannot read palette frame");
            break;

            default:
            g_warning("Unknown frame type %d", frame->type);
            break;
        }

        p = fstart + frame->size;
    }

    return TRUE;
}"""