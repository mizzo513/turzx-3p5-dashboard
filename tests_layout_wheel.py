# -*- coding: utf-8 -*-
"""Headless regression tests: wheel edits are local until Apply."""
from __future__ import annotations

from types import SimpleNamespace
import unittest

from layout_wheel import wheel_value
from layout_editor import LayoutEditor


class FakeVariable:
    def __init__(self, value, callback=None):
        self.value=str(value)
        self.callback=callback
    def get(self):
        return self.value
    def set(self, value):
        self.value=str(value)
        if self.callback is not None:
            self.callback()


class WheelTests(unittest.TestCase):
    def test_text_coordinate_and_font_steps(self):
        props={'x':20,'y':11,'size':25}
        self.assertEqual(wheel_value('x',20,+1,kind='text',geometry=props),21)
        self.assertEqual(wheel_value('y',11,-1,kind='text',geometry=props),10)
        self.assertEqual(wheel_value('size',25,+1,kind='text',geometry=props,shift=True),35)
        self.assertEqual(wheel_value('size',25,-1,kind='text',geometry=props,shift=True),15)

    def test_coordinate_and_font_limits(self):
        props={'x':479,'y':319,'size':52}
        self.assertEqual(wheel_value('x',479,1,kind='text',geometry=props),479)
        self.assertEqual(wheel_value('y',319,1,kind='text',geometry=props),319)
        self.assertEqual(wheel_value('size',52,1,kind='text',geometry=props),52)
        self.assertEqual(wheel_value('size',8,-1,kind='text',geometry=props),8)

    def test_panel_size_and_bounds(self):
        props={'x':180,'y':94,'w':289,'h':57,'radius':7,'border_width':1}
        self.assertEqual(wheel_value('x',180,+1,kind='panel',geometry=props),181)
        self.assertEqual(wheel_value('x',190,+1,kind='panel',geometry=props),191)
        self.assertEqual(wheel_value('x',192,+1,kind='panel',geometry=props),191)
        self.assertEqual(wheel_value('w',289,+1,kind='panel',geometry=props),290)
        self.assertEqual(wheel_value('w',300,+1,kind='panel',geometry=props),300)
        self.assertEqual(wheel_value('h',226,+1,kind='panel',geometry=props),226)
        self.assertEqual(wheel_value('radius',7,+1,kind='panel',geometry=props,shift=True),17)
        self.assertEqual(wheel_value('border_width',1,-1,kind='panel',geometry=props),0)

    def test_panel_geometry_limits(self):
        props={'x':179,'y':298,'w':300,'h':22}
        self.assertEqual(wheel_value('x',179,1,kind='panel',geometry=props),180)
        self.assertEqual(wheel_value('y',298,1,kind='panel',geometry=props),298)
        self.assertEqual(wheel_value('w',300,1,kind='panel',geometry=props),301)
        self.assertEqual(wheel_value('h',22,1,kind='panel',geometry=props),22)
        self.assertEqual(wheel_value('w',2,-1,kind='panel',geometry=props),2)
        self.assertEqual(wheel_value('border_width',12,1,kind='panel',geometry=props),12)

    def test_non_numeric_and_mismatched_field_refused(self):
        with self.assertRaises(ValueError):
            wheel_value('fill',10,1,kind='panel',geometry={})
        with self.assertRaises(ValueError):
            wheel_value('w',10,1,kind='text',geometry={'x':10,'y':10,'size':12})

    def test_editor_wheel_stages_preview_only(self):
        """No GUI display needed; .save() must NEVER be called by wheel edits."""
        class Gui:
            def save(self):
                raise AssertionError('wheel unexpectedly saved to disk')
        editor=LayoutEditor.__new__(LayoutEditor)
        editor.gui=Gui()
        editor.selected=('text','clock_datetime')
        editor.text_styles={}
        editor.panel_styles={}
        editor.loading=False
        editor.unsaved=False
        editor.status=SimpleNamespace(set=lambda x:None)
        updates=[]
        editor.queue_refresh=lambda:updates.append('preview')
        props=editor.current_props()
        editor.vars={k:FakeVariable(props[k]) for k in ('x','y','size','color')}
        for value in editor.vars.values():
            value.callback=editor.on_field_edit
        result=editor.on_numeric_wheel(SimpleNamespace(delta=120,state=0),'x')
        self.assertEqual(result,'break')
        self.assertEqual(editor.text_styles['clock_datetime']['x'],props['x']+1)
        self.assertTrue(editor.unsaved)
        self.assertEqual(updates,['preview'])
        result=editor.on_numeric_wheel(SimpleNamespace(delta=-120,state=1),'size')
        self.assertEqual(result,'break')
        self.assertEqual(editor.text_styles['clock_datetime']['size'],props['size']-10)
        self.assertEqual(updates,['preview','preview'])

    def test_hidden_field_does_not_change(self):
        class Var:
            def __init__(self):self.val='3'
            def get(self):return self.val
            def set(self,v):raise AssertionError('hidden field must not change')
        editor=LayoutEditor.__new__(LayoutEditor)
        editor.selected=('text','clock_datetime')
        editor.vars={'w':Var()}
        result=editor.on_numeric_wheel(SimpleNamespace(delta=120,state=0),'w')
        self.assertEqual(result,'break')


if __name__=='__main__':
    unittest.main()
