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
        private bool _isDialogOpen = false;  // 添加對話框狀態追蹤

        private bool _isDraggingSlider = false;

        // 滑鼠點擊進度條立即跳段
        private void PlaybackSlider_Tapped(object sender, TappedRoutedEventArgs e)
        {
            if (sender is Slider slider && ViewModel.TotalDuration > 0)
            {
                var position = e.GetPosition(slider);
                double relativeX = position.X / slider.ActualWidth;
                double targetTime = relativeX * slider.Maximum;

                // 更新 ViewModel 播放位置
                ViewModel.SeekTo(targetTime);

                // 手動更新滑塊值，讓 UI 立即反映
                slider.Value = targetTime;
            }
        }

        // 拖曳開始
        private void PlaybackSlider_PointerPressed(object sender, PointerRoutedEventArgs e)
        {
            _isDraggingSlider = true;
        }

        // 拖曳結束
        private void PlaybackSlider_PointerReleased(object sender, PointerRoutedEventArgs e)
        {
            var slider = sender as Slider;
            if (slider != null && ViewModel != null)
            {
                // 取得使用者拖曳結束時的值
                double targetPosition = slider.Value;

                // 執行跳段邏輯（這才是控制實際音訊播放的位置）
                ViewModel.SeekTo(targetPosition);
            }
        }

        // 可選：防止拖曳期間更新進度條 UI（不一定要加）
        private void PlaybackSlider_ValueChanged(object sender, RangeBaseValueChangedEventArgs e)
        {
            if (!_isDraggingSlider && ViewModel.IsPlaying)
            {
                // 如果不是手動拖曳時才更新 ViewModel（保持雙向綁定）
                ViewModel.PlaybackPosition = e.NewValue;
            }
        }



        public MainWindow()
        {
            ViewModel = new MainViewModel();        // x:Bind 前必須先初始化
            this.InitializeComponent();             // 之後才能 Initialize XAML 元件


            // 設定轉換器尋找路徑



            // 初始化錄音計時器
            _recordingTimer = new DispatcherTimer();
            _recordingTimer.Interval = TimeSpan.FromSeconds(1);
            _recordingTimer.Tick += RecordingTimer_Tick;

            // 設置數據綁定
            ViewModel.PropertyChanged += ViewModel_PropertyChanged;

            // 更新UI顯示模式
            UpdateControlPanelVisibility();
        }

        private void RecordingTimer_Tick(object sender, object e)
        {
            // 更新ViewModel中的錄音時間
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

                    // 更新按鈕視覺狀態
                    UpdateRecordingButtonVisuals();

                    // 管理錄音計時器
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

                    // 當處理完成時，刷新控制面板以更新轉錄按鈕顯示
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
                    // 刷新ListView以顯示重新命名的結果
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
            // 不切換畫面，保持在原畫面
            // 只是更新UI狀態顯示錄音中
            // CompactRecordingPanel.Visibility = Visibility.Visible;
            // MainContentGrid.Visibility = Visibility.Collapsed;

            // 可以通過調整某些UI元素來顯示錄音狀態
            // 例如改變錄音按鈕的外觀或添加錄音指示器
        }

        private void HideCompactRecordingMode()
        {
            // 不需要恢復畫面，因為沒有切換
            // CompactRecordingPanel.Visibility = Visibility.Collapsed;
            // MainContentGrid.Visibility = Visibility.Visible;
        }

        private void ShowRecordingCompleteNotification()
        {
            // 移除ContentDialog調用，避免與其他對話框衝突
            // 改用狀態更新來提示錄音完成
            ViewModel.RecordingStatus = "錄音完成";
        }

        private void UpdateControlPanelVisibility()
        {
            if (ViewModel.SelectedRecord == null)
            {
                // 顯示新增錄音面板
                RecordingControlPanel.Visibility = Visibility.Visible;
                PlaybackControlPanel.Visibility = Visibility.Collapsed;
                ControlTitleText.Text = "錄音控制";
            }
            else
            {
                // 顯示播放控制面板
                RecordingControlPanel.Visibility = Visibility.Collapsed;
                PlaybackControlPanel.Visibility = Visibility.Visible;
                ControlTitleText.Text = "播放控制";

                // 檢查是否需要顯示轉錄按鈕
                TranscribeButton.Visibility = ViewModel.SelectedRecord.IsTranscribed ?
                    Visibility.Collapsed : Visibility.Visible;
            }
        }

        private void UpdatePlayPauseIcon()
        {
            PlayPauseIcon.Glyph = ViewModel.IsPlaying ? "\uE103" : "\uE102"; // 暫停 : 播放
        }

        // 新增錄音按鈕點擊
        private void NewRecordingButton_Click(object sender, RoutedEventArgs e)
        {
            // 重置到新錄音狀態
            ViewModel.ResetToNewRecordingState();
        }

        private async void StartRecordingButton_Click(object sender, RoutedEventArgs e)
        {
            // 確保是新錄音狀態
            if (ViewModel.SelectedRecord != null)
            {
                ViewModel.ResetToNewRecordingState();
            }
            await ViewModel.StartNewRecordingAsync();
        }

        private async void StopRecordingButton_Click(object sender, RoutedEventArgs e)
        {
            await ViewModel.StopRecordingAsync();

            // 顯示儲存對話框，並獲取是否需要轉錄
            var shouldTranscribe = await ShowSaveMeetingDialog();

            // 如果用戶選擇轉錄，則開始轉錄
            if (shouldTranscribe)
            {
                await ViewModel.StartTranscriptionAsync();
            }
        }

        private async Task<bool> ShowSaveMeetingDialog()
        {
            if (_isDialogOpen) return false;  // 防止重複開啟

            _isDialogOpen = true;
            try
            {
                var nameTextBox = new TextBox
                {
                    PlaceholderText = "請輸入會議名稱",
                    Text = $"會議記錄 {DateTime.Now:MM/dd HH:mm}"
                };

                var transcribeCheckBox = new CheckBox
                {
                    Content = "完成後進行AI語音轉錄",
                    IsChecked = true
                };

                var dialog = new ContentDialog
                {
                    Title = "儲存會議記錄",
                    Content = new StackPanel
                    {
                        Spacing = 16,
                        Children = { nameTextBox, transcribeCheckBox }
                    },
                    PrimaryButtonText = "確定",
                    SecondaryButtonText = "取消",
                    DefaultButton = ContentDialogButton.Primary,
                    XamlRoot = this.Content.XamlRoot
                };

                var result = await dialog.ShowAsync();
                if (result == ContentDialogResult.Primary && !string.IsNullOrWhiteSpace(nameTextBox.Text))
                {
                    // 修復：確保選中的是最新的記錄
                    var latestRecord = ViewModel.ConferenceRecords.FirstOrDefault();
                    if (latestRecord != null)
                    {
                        latestRecord.Title = nameTextBox.Text;
                        // 通知PropertyChanged以更新UI
                        ViewModel.NotifyPropertyChanged(nameof(ViewModel.ConferenceRecords));

                        // 強制刷新ListView以確保名稱立即生效
                        ConferenceRecordsList.ItemsSource = null;
                        ConferenceRecordsList.ItemsSource = ViewModel.ConferenceRecords;

                        // 確保SelectedRecord指向正確的記錄
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
            if (_isDialogOpen) return;  // 防止重複開啟

            _isDialogOpen = true;
            try
            {
                var dialog = new ContentDialog
                {
                    Title = "語音轉錄",
                    Content = "是否要進行AI語音轉錄？",
                    PrimaryButtonText = "是",
                    SecondaryButtonText = "否",
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
            // 顯示轉錄確認對話框
            await ShowTranscriptionConfirmDialog();
        }

        private async void UploadAudioButton_Click(object sender, RoutedEventArgs e)
        {
            var picker = new FileOpenPicker();

            // 取得視窗控制代碼以便與檔案選擇器配合使用
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

        // 播放/暫停按鈕點擊
        private async void PlayPauseButton_Click(object sender, RoutedEventArgs e)
        {
            await ViewModel.PlayPauseAsync();
        }

        // 快退按鈕點擊
        private void SeekBackward_Click(object sender, RoutedEventArgs e)
        {
            var newPosition = Math.Max(0, ViewModel.PlaybackPosition - 10); // 後退10秒
            ViewModel.SeekTo(newPosition);
        }

        // 快進按鈕點擊
        private void SeekForward_Click(object sender, RoutedEventArgs e)
        {
            var newPosition = Math.Min(ViewModel.TotalDuration, ViewModel.PlaybackPosition + 10); // 前進10秒
            ViewModel.SeekTo(newPosition);
        }

        // 播放進度條值改變


        // 時間戳按鈕點擊
        private void TimestampButton_Click(object sender, RoutedEventArgs e)
        {
            if (sender is HyperlinkButton button && button.Tag is TimeSpan timestamp)
            {
                ViewModel.JumpToTimestamp(timestamp);
            }
        }

        // 匯出轉錄內容
        private async void ExportTranscriptButton_Click(object sender, RoutedEventArgs e)
        {
            if (ViewModel.CurrentTranscriptSegments.Count == 0)
            {
                await ShowMessageDialog("提示", "目前沒有轉錄內容可以匯出。");
                return;
            }

            await ExportTextFile("轉錄內容", GenerateTranscriptText(), "transcript");
        }

        // 匯出摘要內容
        private async void ExportSummaryButton_Click(object sender, RoutedEventArgs e)
        {
            if (string.IsNullOrWhiteSpace(ViewModel.Summary))
            {
                await ShowMessageDialog("提示", "目前沒有摘要內容可以匯出。");
                return;
            }

            await ExportTextFile("會議摘要", ViewModel.Summary, "summary");
        }

        private string GenerateTranscriptText()
        {
            var content = $"會議轉錄內容\n";
            content += $"生成時間：{DateTime.Now:yyyy/MM/dd HH:mm:ss}\n\n";

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
                picker.FileTypeChoices.Add("文字檔案", new List<string>() { ".txt" });
                picker.SuggestedFileName = $"{filePrefix}_{DateTime.Now:yyyyMMdd_HHmmss}";

                var file = await picker.PickSaveFileAsync();
                if (file != null)
                {
                    CachedFileManager.DeferUpdates(file);
                    await FileIO.WriteTextAsync(file, content);
                    var status = await CachedFileManager.CompleteUpdatesAsync(file);

                    if (status == FileUpdateStatus.Complete)
                    {
                        await ShowMessageDialog("匯出成功", $"{title}已成功匯出到：\n{file.Path}");
                    }
                    else
                    {
                        await ShowMessageDialog("匯出失敗", "檔案匯出時發生錯誤。");
                    }
                }
            }
            catch (Exception ex)
            {
                await ShowMessageDialog("錯誤", $"匯出時發生錯誤：{ex.Message}");
            }
        }

        private async Task ShowMessageDialog(string title, string message)
        {
            if (_isDialogOpen) return;  // 防止重複開啟

            _isDialogOpen = true;
            try
            {
                var dialog = new ContentDialog
                {
                    Title = title,
                    Content = message,
                    CloseButtonText = "確定",
                    XamlRoot = this.Content.XamlRoot
                };

                await dialog.ShowAsync();
            }
            finally
            {
                _isDialogOpen = false;
            }
        }

        // 重新命名會議記錄
        private async void RenameRecordButton_Click(object sender, RoutedEventArgs e)
        {
            if (_isDialogOpen) return;  // 防止重複開啟

            if (sender is Button button && button.Tag is ConferenceRecord record)
            {
                _isDialogOpen = true;
                try
                {
                    var dialog = new ContentDialog
                    {
                        Title = "重新命名會議",
                        PrimaryButtonText = "確定",
                        SecondaryButtonText = "取消",
                        DefaultButton = ContentDialogButton.Primary,
                        XamlRoot = this.Content.XamlRoot
                    };

                    var textBox = new TextBox
                    {
                        PlaceholderText = "請輸入新的會議名稱",
                        Text = record.Title
                    };

                    dialog.Content = textBox;

                    var result = await dialog.ShowAsync();
                    if (result == ContentDialogResult.Primary && !string.IsNullOrWhiteSpace(textBox.Text))
                    {
                        record.Title = textBox.Text;
                        // 通知PropertyChanged以更新UI
                        ViewModel.NotifyPropertyChanged(nameof(ViewModel.ConferenceRecords));

                        // 強制刷新ListView
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

        // 音訊設備選擇事件


        private void OutputDeviceComboBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
        {
            if (sender is ComboBox comboBox && comboBox.SelectedItem is ComboBoxItem selectedItem)
            {
                // 這裡可以添加實際的音訊設備切換邏輯
                // 例如：AudioManager.SetOutputDevice(selectedItem.Content.ToString());
            }
        }
    }
}
// 注意：這個MainWindow.xaml.cs文件是用於ConferenceAssistant應用程序的主窗口邏輯。窗口邏輯。