from django import forms

from .models import Project


class ChatMessageForm(forms.Form):
    content = forms.CharField(
        label="消息内容",
        max_length=4000,
        widget=forms.Textarea(
            attrs={"rows": 4, "placeholder": "输入你的需求内容（Shift+Enter 换行），或使用麦克风语音输入"}
        ),
        required=False,  # 允许仅发送附件而不填写文本
    )
    attachment = forms.FileField(
        label="上传附件",
        required=False,
        widget=forms.ClearableFileInput(attrs={"style": "margin-top: 10px;"}),
    )


class ProjectForm(forms.ModelForm):
    """项目表单"""
    # 将 path 设为可选，如果不填则默认放在 core 同级目录
    path = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-mindforge', 'placeholder': '留空则默认放在 core 同级目录，或输入路径如：test 或 /path/to/project'}),
        label='项目路径',
        help_text='支持相对路径（相对于 core 的父目录）或绝对路径。需求文档将保存到项目路径下的 doc/01-or 文件夹'
    )

    class Meta:
        model = Project
        fields = ['name', 'path', 'description', 'is_default']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-mindforge', 'placeholder': '项目名称'}),
            'description': forms.Textarea(attrs={'class': 'form-mindforge', 'rows': 3, 'placeholder': '项目描述（可选）'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': '项目名称',
            'description': '项目描述',
            'is_default': '设为默认项目',
        }

