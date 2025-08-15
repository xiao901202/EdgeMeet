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
                new PropertyMetadata("�ǳƴN��", OnStatusTextChanged));

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
                    // �����ɡG��� bar �ܬ���A���ܾ��]�ܬ���
                    RecordingIndicator.Fill = new SolidColorBrush(Colors.Red);
                    MainBorder.Background = new SolidColorBrush(Colors.Red);
                    MainBorder.BorderBrush = new SolidColorBrush(Colors.DarkRed);
                    
                    // ����r�ܬ��զ�H�O���iŪ��
                    if (StatusTextBlock != null)
                    {
                        StatusTextBlock.Foreground = new SolidColorBrush(Colors.White);
                    }

                    // ��ܨö}�l�I�l�ʵe
                    PulseIndicator.Visibility = Visibility.Visible;
                    if (RecordingPulseAnimation != null)
                    {
                        RecordingPulseAnimation.Begin();
                    }
                }
                else
                {
                    // �D�����ɡG��_�q�{�C��
                    RecordingIndicator.Fill = new SolidColorBrush(Colors.Gray);
                    MainBorder.Background = (Brush)Application.Current.Resources["CardBackgroundFillColorDefaultBrush"];
                    MainBorder.BorderBrush = (Brush)Application.Current.Resources["CardStrokeColorDefaultBrush"];
                    
                    // ��_��r���q�{�C��
                    if (StatusTextBlock != null)
                    {
                        StatusTextBlock.ClearValue(TextBlock.ForegroundProperty);
                    }

                    // ���èð���I�l�ʵe
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
            // AudioLevelBar �w�Q�����A�p�G�ݭn�i�H�q�L��L�覡��ܭ��T���šA�Ҧp�վ���ܾ��j�p���C��
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