using System.Collections.Generic;

namespace ConferenceAssistant.Models
{
    public class ConferenceRecordDto
    {
        public string Id { get; set; } = "";
        public string Title { get; set; } = "";
        public string Date { get; set; } = "";
        public double Duration { get; set; }
        public string FilePath { get; set; } = "";
        public string Summary { get; set; } = "";
        public bool IsTranscribed { get; set; }
        public List<TranscriptSegmentDto> TranscriptSegments { get; set; } = new();
    }

    public class TranscriptSegmentDto
    {
        public int Timestamp { get; set; }
        public string Text { get; set; } = "";
        public string Speaker { get; set; } = "";
    }
}
