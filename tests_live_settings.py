from __future__ import annotations
import unittest, tempfile, json
from datetime import datetime
from PIL import Image
import turzx_dashboard as m

class TestLive(unittest.TestCase):
    def test_clock_compact_rect_is_small_and_in_bounds(self):
        r=m.rotation_region(m.seconds_region(m.DEFAULTS,datetime(2026,11,18,10,30,12,tzinfo=m.TZ)))
        assert 0<=r[0]<r[2]<=480 and 0<=r[1]<r[3]<=320,r
        assert (r[2]-r[0])*(r[3]-r[1])*2 < 5000
    def test_render_clock_all_same_size_and_region_change(self):
        t=datetime(2026,11,18,10,30,12,tzinfo=m.TZ)
        conf=m.DEFAULTS.copy()
        w=m.Weather(city='白山市'); trains=m.TrainState()
        a=m.render_physical(t,w,trains,conf)
        b=m.render_physical(t.replace(second=13),w,trains,conf)
        assert a.size==(480,320)
        assert b.size==(480,320)
        a1=a.crop(m.rotation_region(m.seconds_region(m.DEFAULTS,datetime(2026,11,18,10,30,12,tzinfo=m.TZ))))
        b1=b.crop(m.rotation_region(m.seconds_region(m.DEFAULTS,datetime(2026,11,18,10,30,12,tzinfo=m.TZ))))
        self.assertNotEqual(a1.tobytes(),b1.tobytes())
        box=m.rotation_region(m.seconds_region(m.DEFAULTS,datetime(2026,11,18,10,30,12,tzinfo=m.TZ)))
        diff=a.copy();diff.paste(b1,(box[0],box[1]))
        self.assertEqual(diff.tobytes(),b.tobytes(), 'Changing seconds must not affect pixels outside its crop')
    def test_minutes_update_fits_clock_region(self):
        t=datetime(2026,11,18,10,30,59,tzinfo=m.TZ)
        conf=m.DEFAULTS.copy();w=m.Weather(); trains=m.TrainState()
        a=m.render_physical(t,w,trains,conf)
        b=m.render_physical(t.replace(minute=31,second=0),w,trains,conf)
        cropped=m.rotation_region((0,0,480,58))
        new=a.copy();new.paste(b.crop(cropped),(cropped[0],cropped[1]))
        self.assertEqual(new.tobytes(),b.tobytes())
    def test_no_seconds_mode(self):
        conf=m.DEFAULTS.copy();conf['show_seconds']=False
        t=datetime(2026,11,18,10,30,0,tzinfo=m.TZ)
        w=m.Weather(); train=m.TrainState()
        self.assertEqual(m.render_physical(t,w,train,conf).tobytes(),m.render_physical(t.replace(second=49),w,train,conf).tobytes())
    def test_byte_count_and_partial_packet(self):
        box=m.rotation_region(m.seconds_region(m.DEFAULTS,datetime(2026,11,18,10,30,12,tzinfo=m.TZ)))
        im=Image.new('RGB',(box[2]-box[0],box[3]-box[1]))
        commands=[]
        class SerialMock:
            def write(self, data):commands.append(bytes(data)); return len(data)
            def flush(self):pass
        m.send_bitmap(SerialMock(),im,box[0],box[1])
        assert commands[0]==m.region_packet(box[0],box[1],box[2]-1,box[3]-1)
        assert sum(len(v) for v in commands[1:])==2*im.width*im.height
    def test_config_defaults(self):
        self.assertEqual(m.DEFAULTS['clock_update_mode'],'compact')
        self.assertTrue(m.DEFAULTS['show_seconds'])

if __name__=='__main__':unittest.main(verbosity=2)
