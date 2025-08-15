using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Animation;
using Microsoft.UI;

namespace ConferenceAssistant.Controls
{
    public sealed partial class RecordingStatusControl : UserControl
    {
        public static readonly DependencyProperty IsRecordingProperty =
            DependencyProperty.Register(nameof(IsRecording), typeof(bool), typeof(RecordingStatusControl), 
                new PropertyMetadata(false, OnIsRecordingChanged));

        public static readonly DependencyProperty AudioLevelProperty =
            DependencyProperty.Register(nameof(AudioLevel), typeof(double), typeof(RecordingStatusControl), 
                new PropertyMetadata(0.0, OnAudioLevelChanged));

        public static readonly DependencyProperty StatusTextProperty =
            DependencyProperty.Register(nameof(StatusText), typeof(string), typeof(RecordingStatusControl), 
                new PropertyMetadata("準備就緒", OnStatusTextChanged));

        public RecordingStatusControl()
        {
            this.InitializeComponent();
        }

        public bool IsRecording
        {
            get => (bool)GetValue(IsRecordingProperty);
            set => SetValue(IsRecordingProperty, value);
        }

        public double AudioLevel
        {
            get => (double)GetValue(AudioLevelProperty);
            set => SetValue(AudioLevelProperty, value);
        }

        public string StatusText
        {
            get => (string)GetValue(StatusTextProperty);
            set => SetValue(StatusTextProperty, value);
        }

        private static void OnIsRecordingChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
        {
            if (d is RecordingStatusControl control)
            {
                control.UpdateRecordingState();
            }
        }

        private static void OnAudioLevelChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
        {
            if (d is RecordingStatusControl control)
            {
                control.UpdateAudioLevel();
            }
        }

        private static void OnStatusTextChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
        {
            if (d is RecordingStatusControl control)
            {
                control.UpdateStatusText();
            }
        }

        private void UpdateRecordingState()
        {
            if (RecordingIndicator != null && MainBorder != null && PulseIndicator != null)
            {
                if (IsRecording)
                {
                    // 錄音時：整個 bar 變紅色，指示器也變紅色
                    RecordingIndicator.Fill = new SolidColorBrush(Colors.Red);
                    MainBorder.Background = new SolidColorBrush(Colors.Red);
                    MainBorder.BorderBrush = new SolidColorBrush(Colors.DarkRed);
                    
                    // 讓文字變為白色以保持可讀性
                    if (StatusTextBlock != null)
                    {
                        StatusTextBlock.Foreground = new SolidColorBrush(Colors.White);
                    }

                    // 顯示並開始呼吸動畫
                    PulseIndicator.Visibility = Visibility.Visible;
                    if (RecordingPulseAnimation != null)
                    {
                        RecordingPulseAnimation.Begin();
                    }
                }
                else
                {
                    // 非錄音時：恢復默認顏色
                    RecordingIndicator.Fill = new SolidColorBrush(Colors.Gray);
                    MainBorder.Background = (Brush)Application.Current.Resources["CardBackgroundFillColorDefaultBrush"];
                    MainBorder.BorderBrush = (Brush)Application.Current.Resources["CardStrokeColorDefaultBrush"];
                    
                    // 恢復文字的默認顏色
                    if (StatusTextBlock != null)
                    {
                        StatusTextBlock.ClearValue(TextBlock.ForegroundProperty);
                    }

                    // 隱藏並停止呼吸動畫
                    PulseIndicator.Visibility = Visibility.Collapsed;
                    if (RecordingPulseAnimation != null)
                    {
                        RecordingPulseAnimation.Stop();
                    }
                }
            }
        }

        private void UpdateAudioLevel()
        {
            // AudioLevelBar 已被移除，如果需要可以通過其他方式顯示音訊等級，例如調整指示器大小或顏色
        }

        private void UpdateStatusText()
        {
            if (StatusTextBlock != null)
            {
                StatusTextBlock.Text = StatusText;
            }
        }
    }
}