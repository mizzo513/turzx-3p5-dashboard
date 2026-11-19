# SPDX-License-Identifier: GPL-3.0-or-later
"""Ten local Tk settings-window palettes (not USB display themes).

Only the settings UI uses this table. It is deliberately free of tkinter
imports so stored names can be validated by the headless renderer.
"""
from __future__ import annotations

DEFAULT_PRESET = '標準ブルー'

# Surface/background, text, tabs (idle/active/selected), accent and controls.
# All colors are fixed RGB literals: no network or user-supplied CSS.
PRESETS = {
    '標準ブルー': dict(window='#E3EBF2', surface='#F7FAFD', ink='#23394F',
        muted='#435D72', tab='#CEDAE5', hover='#AACFE3', selected='#17638D',
        selected_ink='#FFFFFF', hover_ink='#123F58', border='#7997AC',
        button='#DAE7EF', button_ink='#23394F', field='#FFFFFF', accent='#21709C'),
    'ライトグレー': dict(window='#E8E9ED', surface='#FFFFFF', ink='#30353E',
        muted='#525C65', tab='#D8DAE0', hover='#BABFC9', selected='#485A71',
        selected_ink='#FFFFFF', hover_ink='#202936', border='#858D99',
        button='#E0E3E9', button_ink='#26313D', field='#FFFFFF', accent='#365C82'),
    'ダークネイビー': dict(window='#152234', surface='#1C3045', ink='#ECF5FF',
        muted='#C7D5E4', tab='#2B4259', hover='#405D77', selected='#2681A8',
        selected_ink='#FFFFFF', hover_ink='#FFFFFF', border='#577A91',
        button='#30485F', button_ink='#FFFFFF', field='#213449', accent='#94DFFF'),
    'フォレスト': dict(window='#E5EEE6', surface='#F7FCF7', ink='#243C2D',
        muted='#46634D', tab='#C8DCCB', hover='#9EC5A8', selected='#276D4A',
        selected_ink='#FFFFFF', hover_ink='#173C2C', border='#789A80',
        button='#D4E9D7', button_ink='#214632', field='#FFFFFF', accent='#205F44'),
    'ミント': dict(window='#DFF3ED', surface='#F7FFFC', ink='#1F4645',
        muted='#3C6663', tab='#BDE6DC', hover='#8CD7C4', selected='#16766C',
        selected_ink='#FFFFFF', hover_ink='#163D38', border='#6DADA4',
        button='#CAF0E4', button_ink='#1E4C49', field='#FFFFFF', accent='#126F67'),
    'パープル': dict(window='#EBE7F5', surface='#FCFAFF', ink='#392D56',
        muted='#605278', tab='#DAD1ED', hover='#BEADE0', selected='#6544A0',
        selected_ink='#FFFFFF', hover_ink='#2C2152', border='#9785BD',
        button='#E0D8F0', button_ink='#352854', field='#FFFFFF', accent='#6846A0'),
    'サンセット': dict(window='#F8EBDF', surface='#FFFAF4', ink='#503327',
        muted='#755342', tab='#F1D7BF', hover='#E9B993', selected='#AF5938',
        selected_ink='#FFFFFF', hover_ink='#582D1C', border='#C99979',
        button='#F3DDC9', button_ink='#513324', field='#FFFFFF', accent='#A34A31'),
    'ローズ': dict(window='#F6E8ED', surface='#FFFAFC', ink='#502B3D',
        muted='#755269', tab='#ECCFDA', hover='#DDB0C3', selected='#A63D6A',
        selected_ink='#FFFFFF', hover_ink='#5C2741', border='#B87C97',
        button='#F2D9E2', button_ink='#532E41', field='#FFFFFF', accent='#9C315C'),
    'モノクローム': dict(window='#E9E9E9', surface='#FFFFFF', ink='#1E1E1E',
        muted='#464646', tab='#CDCDCD', hover='#AFAFAF', selected='#383838',
        selected_ink='#FFFFFF', hover_ink='#111111', border='#7C7C7C',
        button='#E0E0E0', button_ink='#202020', field='#FFFFFF', accent='#333333'),
    '高コントラスト': dict(window='#080F19', surface='#101E31', ink='#FFFFFF',
        muted='#E9F4FF', tab='#24364A', hover='#3E5876', selected='#F3CF42',
        selected_ink='#111827', hover_ink='#FFFFFF', border='#D6DEEC',
        button='#2D435D', button_ink='#FFFFFF', field='#142740', accent='#FFDB5F'),
}


def palette(name):
    """Return a named preset, falling back to the default for old settings."""
    return PRESETS.get(name, PRESETS[DEFAULT_PRESET])


def validate_preset(name):
    if name not in PRESETS:
        raise ValueError('設定画面の配色プリセットを選び直してください。')
    return name
