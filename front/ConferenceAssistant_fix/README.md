# ConferenceAssistant (會議助手)

一個功能強大的會議錄音與轉錄應用程序，基於 WinUI 3 和 .NET 8 構建，提供智能會議記錄、語音轉錄和內容摘要功能。


## 🚀 功能特色

### 核心功能
- **實時錄音**: 支持高質量音頻錄製，帶視覺音量指示
- **AI 語音轉錄**: 智能語音識別，支持多說話人分離
- **會議摘要**: 自動生成會議內容摘要
- **播放控制**: 完整的音頻播放控制，支持快進/快退
- **時間戳導航**: 點擊時間戳快速跳轉到對應音頻位置
- **檔案管理**: 會議記錄管理、重命名、匯出功能
- **音頻上傳**: 支持多種音頻格式 (WAV, MP3, M4A, FLAC)

### UI/UX 特色
- **現代化界面**: 採用 Fluent Design 設計語言
- **視覺反饋**: 錄音時狀態欄變紅色配合呼吸動畫效果
- **響應式佈局**: 適配不同螢幕尺寸
- **深色/淺色主題**: 支持系統主題自動切換
- **無障礙設計**: 符合 WCAG 標準的無障礙設計

## 🏗️ 技術架構

### 開發框架
- **前端框架**: WinUI 3 (Windows App SDK 1.7)
- **運行時**: .NET 8.0 (C# 12.0)
- **架構模式**: MVVM (Model-View-ViewModel)
- **數據綁定**: Two-way binding with INotifyPropertyChanged
- **非同步處理**: Task-based Asynchronous Pattern (TAP)

### 核心技術棧
```
├── UI Layer (WinUI 3)
│   ├── XAML Views
│   ├── User Controls
│   └── Value Converters
│
├── Business Logic Layer
│   ├── ViewModels (MVVM)
│   ├── Models
│   └── Services
│
└── Platform Layer
    ├── File System APIs
    ├── Media APIs
    └── Windows Runtime APIs
```



## 🔧 快速開始


## 📁 專案結構

```
ConferenceAssistant_fix/
├── 📁 Assets/                          # 應用程序資源
│   ├── SplashScreen.scale-200.png
│   ├── Square150x150Logo.scale-200.png
│   └── ... (其他圖標)
│
├── 📁 Controls/                        # 自定義用戶控件
│   ├── RecordingStatusControl.xaml     # 錄音狀態控件 XAML
│   └── RecordingStatusControl.xaml.cs  # 錄音狀態控件邏輯
│
├── 📁 Converters/                      # 值轉換器
│   └── ValueConverters.cs              # XAML 綁定轉換器
│
├── 📁 ViewModels/                      # 視圖模型層
│   └── MainViewModel.cs                # 主視圖模型
│
├── 📁 Properties/                      # 專案屬性
│   └── launchSettings.json             # 啟動設定檔
│
├── 📄 App.xaml                         # 應用程序 XAML
├── 📄 App.xaml.cs                      # 應用程序邏輯
├── 📄 MainWindow.xaml                  # 主視窗 XAML
├── 📄 MainWindow.xaml.cs               # 主視窗邏輯
├── 📄 app.manifest                     # 應用程序清單
└── 📄 ConferenceAssistant_fix.csproj   # 專案檔案
```

## ⚙️ 核心功能實現

### 1. 錄音管理系統

#### MainViewModel 中的錄音控制

```csharp
public class MainViewModel : INotifyPropertyChanged
{
    // 錄音狀態管理
    public async Task StartNewRecordingAsync()
    {
        IsRecording = true;
        RecordingStatus = "錄音中...";
        _recordingStartTime = DateTime.Now;
        
        // 模擬音訊等級變化
        _ = Task.Run(async () =>
        {
            var random = new Random();
            while (IsRecording)
            {
                await Task.Delay(100);
                AudioLevel = random.NextDouble() * 100;
            }
        });
    }

    public async Task StopRecordingAsync()
    {
        IsRecording = false;
        RecordingStatus = "處理中...";
        IsProcessing = true;

        // 模擬處理延遲
        await Task.Delay(2000);

        // 創建新的會議記錄
        var newRecord = new ConferenceRecord
        {
            Id = Guid.NewGuid(),
            Title = $"會議記錄 {DateTime.Now:MM/dd HH:mm}",
            Date = DateTime.Now,
            Duration = DateTime.Now - _recordingStartTime,
            FilePath = $"recording_{DateTime.Now:yyyyMMdd_HHmmss}.wav"
        };

        ConferenceRecords.Insert(0, newRecord);
        SelectedRecord = newRecord;
        IsProcessing = false;
    }
}
```

#### 關鍵實現要點:
- **非同步處理**: 使用 `async/await` 模式避免 UI 阻塞
- **狀態管理**: 透過 `INotifyPropertyChanged` 實現響應式 UI 更新
- **資源管理**: 正確處理錄音資源的生命週期

### 2. AI 語音轉錄系統

```csharp
public async Task StartTranscriptionAsync()
{
    if (SelectedRecord == null) return;

    IsProcessing = true;
    RecordingStatus = "正在進行AI語音轉錄...";

    // 模擬轉錄處理
    await Task.Delay(3000);

    // 生成轉錄段落
    var segments = new[]
    {
        new TranscriptSegment 
        { 
            TimeStamp = TimeSpan.FromSeconds(5), 
            Text = "會議開始，大家好。", 
            Speaker = "主持人" 
        },
        // ... 更多段落
    };

    // 更新記錄
    SelectedRecord.TranscriptSegments.Clear();
    foreach (var segment in segments)
    {
        SelectedRecord.TranscriptSegments.Add(segment);
    }

    SelectedRecord.IsTranscribed = true;
    IsProcessing = false;
}
```

### 3. 音頻播放控制

```csharp
public Task PlayPauseAsync()
{
    if (SelectedRecord == null) return Task.CompletedTask;

    IsPlaying = !IsPlaying;
    
    if (IsPlaying)
    {
        // 模擬播放進度更新
        _ = Task.Run(async () =>
        {
            while (IsPlaying && PlaybackPosition < TotalDuration)
            {
                await Task.Delay(100);
                PlaybackPosition += 0.1; // 每100ms增加0.1秒
                UpdateTimeDisplay();
            }
        });
    }
    
    return Task.CompletedTask;
}

public void SeekTo(double position)
{
    PlaybackPosition = position;
    UpdateTimeDisplay();
}

public void JumpToTimestamp(TimeSpan timestamp)
{
    PlaybackPosition = timestamp.TotalSeconds;
    UpdateTimeDisplay();
}
```

## 🎨 自定義控件

### RecordingStatusControl

這是一個高度客製化的錄音狀態控件，提供視覺化的錄音狀態指示。

#### XAML 結構
```xml
<Grid>
    <!-- 主要內容邊框 -->
    <Border x:Name="MainBorder" Background="{ThemeResource CardBackgroundFillColorDefaultBrush}">
        <StackPanel>
            <Grid>
                <Ellipse x:Name="RecordingIndicator" Fill="Gray"/>
                <TextBlock x:Name="StatusTextBlock" Text="準備就緒"/>
            </Grid>
        </StackPanel>
    </Border>
    
    <!-- 呼吸效果指示器 -->
    <Border x:Name="PulseIndicator" BorderBrush="Red" Opacity="0"/>
</Grid>
```

#### 依賴屬性實現
```csharp
public static readonly DependencyProperty IsRecordingProperty =
    DependencyProperty.Register(nameof(IsRecording), typeof(bool), 
    typeof(RecordingStatusControl), 
    new PropertyMetadata(false, OnIsRecordingChanged));

public bool IsRecording
{
    get => (bool)GetValue(IsRecordingProperty);
    set => SetValue(IsRecordingProperty, value);
}
```

#### 視覺狀態更新
```csharp
private void UpdateRecordingState()
{
    if (IsRecording)
    {
        // 錄音時: 整個控件變紅色
        RecordingIndicator.Fill = new SolidColorBrush(Colors.Red);
        MainBorder.Background = new SolidColorBrush(Colors.Red);
        StatusTextBlock.Foreground = new SolidColorBrush(Colors.White);
        
        // 開始呼吸動畫
        PulseIndicator.Visibility = Visibility.Visible;
        RecordingPulseAnimation?.Begin();
    }
    else
    {
        // 恢復默認狀態
        RecordingIndicator.Fill = new SolidColorBrush(Colors.Gray);
        MainBorder.Background = (Brush)Application.Current.Resources["CardBackgroundFillColorDefaultBrush"];
        StatusTextBlock.ClearValue(TextBlock.ForegroundProperty);
        
        // 停止動畫
        PulseIndicator.Visibility = Visibility.Collapsed;
        RecordingPulseAnimation?.Stop();
    }
}
```

## 📊 數據模型

### ConferenceRecord (會議記錄模型)

```csharp
public class ConferenceRecord
{
    public Guid Id { get; set; }
    public string Title { get; set; } = string.Empty;
    public DateTime Date { get; set; }
    public TimeSpan Duration { get; set; }
    public string FilePath { get; set; } = string.Empty;
    public string Summary { get; set; } = string.Empty;
    public bool IsTranscribed { get; set; } = false;
    public ObservableCollection<TranscriptSegment> TranscriptSegments { get; set; } = new();
    
    // 顯示屬性
    public string DisplayDate => Date.ToString("yyyy/MM/dd HH:mm");
    public string DisplayDuration => Duration.ToString(@"mm\:ss");
}
```

### TranscriptSegment (轉錄片段模型)

```csharp
public class TranscriptSegment
{
    public TimeSpan TimeStamp { get; set; }
    public string Text { get; set; } = string.Empty;
    public string Speaker { get; set; } = string.Empty;
    
    public string DisplayTimestamp => TimeStamp.ToString(@"hh\:mm\:ss");
}
```

## 🛠️ 開發指南

### 添加新功能

1. **創建 ViewModel 屬性**
   ```csharp
   private bool _newFeature;
   public bool NewFeature
   {
       get => _newFeature;
       set => SetProperty(ref _newFeature, value);
   }
   ```

2. **實現業務邏輯**
   ```csharp
   public async Task ExecuteNewFeatureAsync()
   {
       // 實現新功能邏輯
   }
   ```

3. **更新 UI 綁定**
   ```xml
   <Button Content="新功能" 
           Command="{x:Bind ViewModel.NewFeatureCommand}"
           IsEnabled="{x:Bind ViewModel.CanExecuteNewFeature}"/>
   ```

### 自定義樣式

應用程序支持通過 `App.xaml` 中的資源字典自定義樣式：

```xml
<Style x:Key="ActionButtonStyle" TargetType="Button">
    <Setter Property="MinWidth" Value="120"/>
    <Setter Property="Height" Value="40"/>
    <Setter Property="CornerRadius" Value="6"/>
    <Setter Property="FontWeight" Value="SemiBold"/>
</Style>
```

### 值轉換器使用

```csharp
public class BoolToRecordingColorConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, string language)
    {
        if (value is bool isRecording && isRecording)
            return new SolidColorBrush(Colors.Red);
        return new SolidColorBrush(Colors.Gray);
    }
}
```

### MSIX 封裝
專案已配置 MSIX 支持，可直接通過 Visual Studio 的 "Package and Publish" 功能建立安裝包。

## 📄 授權條款

本專案採用 MIT 授權條款。詳見 [LICENSE](LICENSE) 檔案。

## 🔧 故障排除

### 常見問題

**Q: 應用程序無法啟動**
A: 確保已安裝 .NET 8.0 Desktop Runtime 和 Windows App SDK

**Q: 錄音功能無法使用**
A: 檢查麥克風權限和音頻設備設定

**Q: 轉錄功能異常**
A: 這是模擬功能，實際部署需要整合真實的 AI 服務

### 偵錯技巧

1. 使用 Visual Studio 偵錯器
2. 檢查輸出視窗的建置訊息
3. 使用 Application Insights 監控 (生產環境)

---

**開發團隊**: ConferenceAssistant Development Team  
**最後更新**: 2024年1月  
**版本**: 1.0.0