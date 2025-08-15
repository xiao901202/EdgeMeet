using ConferenceAssistant.ViewModels;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Data;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Navigation;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices.WindowsRuntime;
using System.Threading.Tasks;
using Windows.ApplicationModel.DataTransfer;
using Windows.Foundation;
using Windows.Foundation.Collections;
using Windows.Storage;
using Windows.Storage.Pickers;
using Windows.Storage.Provider;

namespace ConferenceAssistant
{
    /// <summary>
    /// An empty window that can be used on its own or navigated to within a Frame.
    /// </summary>
    public sealed partial class MainWindow : Window
    {
        public MainViewModel ViewModel { get; }

        private DispatcherTimer _recordingTimer;
        private bool _isDialogOpen = false;  // �K�[��ܮت��A�l��

        private bool _isDraggingSlider = false;

        // �ƹ��I���i�ױ��ߧY���q
        private void PlaybackSlider_Tapped(object sender, TappedRoutedEventArgs e)
        {
            if (sender is Slider slider && ViewModel.TotalDuration > 0)
            {
                var position = e.GetPosition(slider);
                double relativeX = position.X / slider.ActualWidth;
                double targetTime = relativeX * slider.Maximum;

                // ��s ViewModel �����m
                ViewModel.SeekTo(targetTime);

                // ��ʧ�s�ƶ��ȡA�� UI �ߧY�ϬM
                slider.Value = targetTime;
            }
        }

        // �즲�}�l
        private void PlaybackSlider_PointerPressed(object sender, PointerRoutedEventArgs e)
        {
            _isDraggingSlider = true;
        }

        // �즲����
        private void PlaybackSlider_PointerReleased(object sender, PointerRoutedEventArgs e)
        {
            var slider = sender as Slider;
            if (slider != null && ViewModel != null)
            {
                // ���o�ϥΪ̩즲�����ɪ���
                double targetPosition = slider.Value;

                // ������q�޿�]�o�~�O�����ڭ��T���񪺦�m�^
                ViewModel.SeekTo(targetPosition);
            }
        }

        // �i��G����즲������s�i�ױ� UI�]���@�w�n�[�^
        private void PlaybackSlider_ValueChanged(object sender, RangeBaseValueChangedEventArgs e)
        {
            if (!_isDraggingSlider && ViewModel.IsPlaying)
            {
                // �p�G���O��ʩ즲�ɤ~��s ViewModel�]�O�����V�j�w�^
                ViewModel.PlaybackPosition = e.NewValue;
            }
        }



        public MainWindow()
        {
            ViewModel = new MainViewModel();        // x:Bind �e��������l��
            this.InitializeComponent();             // ����~�� Initialize XAML ����


            // �]�w�ഫ���M����|



            // ��l�ƿ����p�ɾ�
            _recordingTimer = new DispatcherTimer();
            _recordingTimer.Interval = TimeSpan.FromSeconds(1);
            _recordingTimer.Tick += RecordingTimer_Tick;

            // �]�m�ƾڸj�w
            ViewModel.PropertyChanged += ViewModel_PropertyChanged;

            // ��sUI��ܼҦ�
            UpdateControlPanelVisibility();
        }

        private void RecordingTimer_Tick(object sender, object e)
        {
            // ��sViewModel���������ɶ�
            ViewModel.UpdateRecordingTime();
        }

        private void ViewModel_PropertyChanged(object sender, System.ComponentModel.PropertyChangedEventArgs e)
        {
            switch (e.PropertyName)
            {
                case nameof(ViewModel.IsRecording):
                    RecordingStatus.IsRecording = ViewModel.IsRecording;
                    StartRecordingButton.IsEnabled = !ViewModel.IsRecording;
                    StopRecordingButton.IsEnabled = ViewModel.IsRecording;
                    CompactStopButton.IsEnabled = ViewModel.IsRecording;

                    // ��s���s��ı���A
                    UpdateRecordingButtonVisuals();

                    // �޲z�����p�ɾ�
                    if (ViewModel.IsRecording)
                    {
                        _recordingTimer.Start();
                        ShowCompactRecordingMode();
                    }
                    else
                    {
                        _recordingTimer.Stop();
                        HideCompactRecordingMode();
                        ShowRecordingCompleteNotification();
                    }
                    break;
                case nameof(ViewModel.AudioLevel):
                    RecordingStatus.AudioLevel = ViewModel.AudioLevel;
                    break;
                case nameof(ViewModel.RecordingStatus):
                    RecordingStatus.StatusText = ViewModel.RecordingStatus;
                    break;
                case nameof(ViewModel.RecordingTime):
                    RecordingTimeText.Text = ViewModel.RecordingTime;
                    CompactRecordingTimeText.Text = ViewModel.RecordingTime;
                    break;
                case nameof(ViewModel.IsProcessing):
                    ProcessingIndicator.Visibility = ViewModel.IsProcessing ? Visibility.Visible : Visibility.Collapsed;
                    UploadAudioButton.IsEnabled = !ViewModel.IsProcessing;

                    // ��B�z�����ɡA��s����O�H��s������s���
                    if (!ViewModel.IsProcessing)
                    {
                        UpdateControlPanelVisibility();
                    }
                    break;
                case nameof(ViewModel.SelectedRecord):
                    UpdateControlPanelVisibility();
                    break;
                case nameof(ViewModel.IsPlaying):
                    UpdatePlayPauseIcon();
                    break;
                case nameof(ViewModel.ConferenceRecords):
                    // ��sListView�H��ܭ��s�R�W�����G
                    break;
            }
        }

        private void UpdateRecordingButtonVisuals()
        {
            if (ViewModel.IsRecording)
            {
                StartRecordingButton.Opacity = 0.5;
                StopRecordingButton.Opacity = 1.0;
            }
            else
            {
                StartRecordingButton.Opacity = 1.0;
                StopRecordingButton.Opacity = 0.5;
            }
        }

        private void ShowCompactRecordingMode()
        {
            // �������e���A�O���b��e��
            // �u�O��sUI���A��ܿ�����
            // CompactRecordingPanel.Visibility = Visibility.Visible;
            // MainContentGrid.Visibility = Visibility.Collapsed;

            // �i�H�q�L�վ�Y��UI��������ܿ������A
            // �Ҧp���ܿ������s���~�[�βK�[�������ܾ�
        }

        private void HideCompactRecordingMode()
        {
            // ���ݭn��_�e���A�]���S������
            // CompactRecordingPanel.Visibility = Visibility.Collapsed;
            // MainContentGrid.Visibility = Visibility.Visible;
        }

        private void ShowRecordingCompleteNotification()
        {
            // ����ContentDialog�եΡA�קK�P��L��ܮؽĬ�
            // ��Ϊ��A��s�Ӵ��ܿ�������
            ViewModel.RecordingStatus = "��������";
        }

        private void UpdateControlPanelVisibility()
        {
            if (ViewModel.SelectedRecord == null)
            {
                // ��ܷs�W�������O
                RecordingControlPanel.Visibility = Visibility.Visible;
                PlaybackControlPanel.Visibility = Visibility.Collapsed;
                ControlTitleText.Text = "��������";
            }
            else
            {
                // ��ܼ��񱱨�O
                RecordingControlPanel.Visibility = Visibility.Collapsed;
                PlaybackControlPanel.Visibility = Visibility.Visible;
                ControlTitleText.Text = "���񱱨�";

                // �ˬd�O�_�ݭn���������s
                TranscribeButton.Visibility = ViewModel.SelectedRecord.IsTranscribed ?
                    Visibility.Collapsed : Visibility.Visible;
            }
        }

        private void UpdatePlayPauseIcon()
        {
            PlayPauseIcon.Glyph = ViewModel.IsPlaying ? "\uE103" : "\uE102"; // �Ȱ� : ����
        }

        // �s�W�������s�I��
        private void NewRecordingButton_Click(object sender, RoutedEventArgs e)
        {
            // ���m��s�������A
            ViewModel.ResetToNewRecordingState();
        }

        private async void StartRecordingButton_Click(object sender, RoutedEventArgs e)
        {
            // �T�O�O�s�������A
            if (ViewModel.SelectedRecord != null)
            {
                ViewModel.ResetToNewRecordingState();
            }
            await ViewModel.StartNewRecordingAsync();
        }

        private async void StopRecordingButton_Click(object sender, RoutedEventArgs e)
        {
            await ViewModel.StopRecordingAsync();

            // ����x�s��ܮءA������O�_�ݭn���
            var shouldTranscribe = await ShowSaveMeetingDialog();

            // �p�G�Τ�������A�h�}�l���
            if (shouldTranscribe)
            {
                await ViewModel.StartTranscriptionAsync();
            }
        }

        private async Task<bool> ShowSaveMeetingDialog()
        {
            if (_isDialogOpen) return false;  // ����ƶ}��

            _isDialogOpen = true;
            try
            {
                var nameTextBox = new TextBox
                {
                    PlaceholderText = "�п�J�|ĳ�W��",
                    Text = $"�|ĳ�O�� {DateTime.Now:MM/dd HH:mm}"
                };

                var transcribeCheckBox = new CheckBox
                {
                    Content = "������i��AI�y�����",
                    IsChecked = true
                };

                var dialog = new ContentDialog
                {
                    Title = "�x�s�|ĳ�O��",
                    Content = new StackPanel
                    {
                        Spacing = 16,
                        Children = { nameTextBox, transcribeCheckBox }
                    },
                    PrimaryButtonText = "�T�w",
                    SecondaryButtonText = "����",
                    DefaultButton = ContentDialogButton.Primary,
                    XamlRoot = this.Content.XamlRoot
                };

                var result = await dialog.ShowAsync();
                if (result == ContentDialogResult.Primary && !string.IsNullOrWhiteSpace(nameTextBox.Text))
                {
                    // �״_�G�T�O�襤���O�̷s���O��
                    var latestRecord = ViewModel.ConferenceRecords.FirstOrDefault();
                    if (latestRecord != null)
                    {
                        latestRecord.Title = nameTextBox.Text;
                        // �q��PropertyChanged�H��sUI
                        ViewModel.NotifyPropertyChanged(nameof(ViewModel.ConferenceRecords));

                        // �j���sListView�H�T�O�W�٥ߧY�ͮ�
                        ConferenceRecordsList.ItemsSource = null;
                        ConferenceRecordsList.ItemsSource = ViewModel.ConferenceRecords;

                        // �T�OSelectedRecord���V���T���O��
                        ViewModel.SelectedRecord = latestRecord;
                    }

                    return transcribeCheckBox.IsChecked == true;
                }

                return false;
            }
            finally
            {
                _isDialogOpen = false;
            }
        }

        private async Task ShowTranscriptionConfirmDialog()
        {
            if (_isDialogOpen) return;  // ����ƶ}��

            _isDialogOpen = true;
            try
            {
                var dialog = new ContentDialog
                {
                    Title = "�y�����",
                    Content = "�O�_�n�i��AI�y������H",
                    PrimaryButtonText = "�O",
                    SecondaryButtonText = "�_",
                    DefaultButton = ContentDialogButton.Primary,
                    XamlRoot = this.Content.XamlRoot
                };

                var result = await dialog.ShowAsync();
                if (result == ContentDialogResult.Primary)
                {
                    await ViewModel.StartTranscriptionAsync();
                }
            }
            finally
            {
                _isDialogOpen = false;
            }
        }

        private async void TranscribeButton_Click(object sender, RoutedEventArgs e)
        {
            // �������T�{��ܮ�
            await ShowTranscriptionConfirmDialog();
        }

        private async void UploadAudioButton_Click(object sender, RoutedEventArgs e)
        {
            var picker = new FileOpenPicker();

            // ���o��������N�X�H�K�P�ɮ׿�ܾ��t�X�ϥ�
            var hwnd = WinRT.Interop.WindowNative.GetWindowHandle(this);
            WinRT.Interop.InitializeWithWindow.Initialize(picker, hwnd);

            picker.ViewMode = PickerViewMode.List;
            picker.SuggestedStartLocation = PickerLocationId.Desktop;
            picker.FileTypeFilter.Add(".wav");
            picker.FileTypeFilter.Add(".mp3");
            picker.FileTypeFilter.Add(".m4a");
            picker.FileTypeFilter.Add(".flac");

            var file = await picker.PickSingleFileAsync();
            if (file != null)
            {
                await ViewModel.UploadAudioFileAsync(file.Path);
            }
        }

        // ����/�Ȱ����s�I��
        private async void PlayPauseButton_Click(object sender, RoutedEventArgs e)
        {
            await ViewModel.PlayPauseAsync();
        }

        // �ְh���s�I��
        private void SeekBackward_Click(object sender, RoutedEventArgs e)
        {
            var newPosition = Math.Max(0, ViewModel.PlaybackPosition - 10); // ��h10��
            ViewModel.SeekTo(newPosition);
        }

        // �ֶi���s�I��
        private void SeekForward_Click(object sender, RoutedEventArgs e)
        {
            var newPosition = Math.Min(ViewModel.TotalDuration, ViewModel.PlaybackPosition + 10); // �e�i10��
            ViewModel.SeekTo(newPosition);
        }

        // ����i�ױ��ȧ���


        // �ɶ��W���s�I��
        private void TimestampButton_Click(object sender, RoutedEventArgs e)
        {
            if (sender is HyperlinkButton button && button.Tag is TimeSpan timestamp)
            {
                ViewModel.JumpToTimestamp(timestamp);
            }
        }

        // �ץX������e
        private async void ExportTranscriptButton_Click(object sender, RoutedEventArgs e)
        {
            if (ViewModel.CurrentTranscriptSegments.Count == 0)
            {
                await ShowMessageDialog("����", "�ثe�S��������e�i�H�ץX�C");
                return;
            }

            await ExportTextFile("������e", GenerateTranscriptText(), "transcript");
        }

        // �ץX�K�n���e
        private async void ExportSummaryButton_Click(object sender, RoutedEventArgs e)
        {
            if (string.IsNullOrWhiteSpace(ViewModel.Summary))
            {
                await ShowMessageDialog("����", "�ثe�S���K�n���e�i�H�ץX�C");
                return;
            }

            await ExportTextFile("�|ĳ�K�n", ViewModel.Summary, "summary");
        }

        private string GenerateTranscriptText()
        {
            var content = $"�|ĳ������e\n";
            content += $"�ͦ��ɶ��G{DateTime.Now:yyyy/MM/dd HH:mm:ss}\n\n";

            foreach (var segment in ViewModel.CurrentTranscriptSegments)
            {
                content += $"[{segment.DisplayTimestamp}] {segment.Speaker}: {segment.Text}\n";
            }

            return content;
        }

        private async Task ExportTextFile(string title, string content, string filePrefix)
        {
            try
            {
                var picker = new FileSavePicker();
                var hwnd = WinRT.Interop.WindowNative.GetWindowHandle(this);
                WinRT.Interop.InitializeWithWindow.Initialize(picker, hwnd);

                picker.SuggestedStartLocation = PickerLocationId.Desktop;
                picker.FileTypeChoices.Add("��r�ɮ�", new List<string>() { ".txt" });
                picker.SuggestedFileName = $"{filePrefix}_{DateTime.Now:yyyyMMdd_HHmmss}";

                var file = await picker.PickSaveFileAsync();
                if (file != null)
                {
                    CachedFileManager.DeferUpdates(file);
                    await FileIO.WriteTextAsync(file, content);
                    var status = await CachedFileManager.CompleteUpdatesAsync(file);

                    if (status == FileUpdateStatus.Complete)
                    {
                        await ShowMessageDialog("�ץX���\", $"{title}�w���\�ץX��G\n{file.Path}");
                    }
                    else
                    {
                        await ShowMessageDialog("�ץX����", "�ɮ׶ץX�ɵo�Ϳ��~�C");
                    }
                }
            }
            catch (Exception ex)
            {
                await ShowMessageDialog("���~", $"�ץX�ɵo�Ϳ��~�G{ex.Message}");
            }
        }

        private async Task ShowMessageDialog(string title, string message)
        {
            if (_isDialogOpen) return;  // ����ƶ}��

            _isDialogOpen = true;
            try
            {
                var dialog = new ContentDialog
                {
                    Title = title,
                    Content = message,
                    CloseButtonText = "�T�w",
                    XamlRoot = this.Content.XamlRoot
                };

                await dialog.ShowAsync();
            }
            finally
            {
                _isDialogOpen = false;
            }
        }

        // ���s�R�W�|ĳ�O��
        private async void RenameRecordButton_Click(object sender, RoutedEventArgs e)
        {
            if (_isDialogOpen) return;  // ����ƶ}��

            if (sender is Button button && button.Tag is ConferenceRecord record)
            {
                _isDialogOpen = true;
                try
                {
                    var dialog = new ContentDialog
                    {
                        Title = "���s�R�W�|ĳ",
                        PrimaryButtonText = "�T�w",
                        SecondaryButtonText = "����",
                        DefaultButton = ContentDialogButton.Primary,
                        XamlRoot = this.Content.XamlRoot
                    };

                    var textBox = new TextBox
                    {
                        PlaceholderText = "�п�J�s���|ĳ�W��",
                        Text = record.Title
                    };

                    dialog.Content = textBox;

                    var result = await dialog.ShowAsync();
                    if (result == ContentDialogResult.Primary && !string.IsNullOrWhiteSpace(textBox.Text))
                    {
                        record.Title = textBox.Text;
                        // �q��PropertyChanged�H��sUI
                        ViewModel.NotifyPropertyChanged(nameof(ViewModel.ConferenceRecords));

                        // �j���sListView
                        ConferenceRecordsList.ItemsSource = null;
                        ConferenceRecordsList.ItemsSource = ViewModel.ConferenceRecords;
                    }
                }
                finally
                {
                    _isDialogOpen = false;
                }
            }
        }

        // ���T�]�ƿ�ܨƥ�


        private void OutputDeviceComboBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
        {
            if (sender is ComboBox comboBox && comboBox.SelectedItem is ComboBoxItem selectedItem)
            {
                // �o�̥i�H�K�[��ڪ����T�]�Ƥ����޿�
                // �Ҧp�GAudioManager.SetOutputDevice(selectedItem.Content.ToString());
            }
        }
    }
}
// �`�N�G�o��MainWindow.xaml.cs���O�Ω�ConferenceAssistant���ε{�Ǫ��D���f�޿�C���f�޿�C