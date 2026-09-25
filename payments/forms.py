from django import forms


class ManualReceiptForm(forms.Form):
    reference = forms.CharField(label="شمارهٔ پیگیری واریز", max_length=80, min_length=4)
    receipt = forms.ImageField(label="تصویر رسید", help_text="فقط تصویر JPG، PNG یا WEBP تا سقف ۵ مگابایت.")

    def clean_receipt(self):
        receipt = self.cleaned_data["receipt"]
        if receipt.size > 5 * 1024 * 1024:
            raise forms.ValidationError("حجم تصویر رسید نباید بیشتر از ۵ مگابایت باشد.")
        return receipt
