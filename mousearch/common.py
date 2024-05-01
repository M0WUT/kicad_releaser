import wx


class BaseDialog:
    def __init__(self, message: str, title: str, style):
        dlg = wx.MessageDialog(
            parent=None,
            message=message,
            caption=title,
            style=style,
        )
        dlg.ShowModal()
        dlg.Destroy()


class InfoDialog(BaseDialog):
    def __init__(self, message: str, title: str):
        super().__init__(message, title, style=wx.OK | wx.ICON_INFORMATION)


class WarningDialog(BaseDialog):
    def __init__(self, message: str, title: str):
        super().__init__(message=message, title=title, style=wx.OK | wx.ICON_WARNING)


class ErrorDialog(BaseDialog):
    def __init__(self, message: str, title: str):
        super().__init__(message=message, title=title, style=wx.OK | wx.ICON_ERROR)
