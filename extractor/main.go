package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"regexp"
	"strconv"
	"strings"
	"time"
)

// ════════════════════════════════════════════════════════════
// OUTPUT SCHEMA v2 — 1 chunk = 1 khoản (multi-law support)
// ════════════════════════════════════════════════════════════

type Document struct {
	ID            string `json:"id"`
	TenVanBan     string `json:"ten_van_ban"`
	SoHieu        string `json:"so_hieu"`
	CoQuanBanHanh string `json:"co_quan_ban_hanh"`
	LoaiVanBan    string `json:"loai_van_ban"`    // luat | nghi-dinh | thong-tu
	NgayBanHanh   string `json:"ngay_ban_hanh"`
	NgayHieuLuc   string `json:"ngay_hieu_luc"`
	NguonURL      string `json:"nguon_url"`
	LawID         string `json:"law_id"`           // slug: lao-dong | bhxh | ...
	ThuTuUuTien   int    `json:"thu_tu_uu_tien"`   // 1=luat, 2=nghi-dinh, 3=thong-tu
	TongSoDieu    int    `json:"tong_so_dieu"`
	TongSoChuong  int    `json:"tong_so_chuong"`
}

type Diem struct {
	KyHieu  string `json:"ky_hieu"`
	NoiDung string `json:"noi_dung"`
}

type Khoan struct {
	SoKhoan  int    `json:"so_khoan"`
	NoiDung  string `json:"noi_dung"`
	DiemList []Diem `json:"diem,omitempty"`
}

type Reference struct {
	TargetDieu   int    `json:"target_dieu"`
	TargetKhoan  int    `json:"target_khoan,omitempty"`
	ContextSnip  string `json:"context_snip"`
	RelationType string `json:"relation_type"`
}

// Chunk v2: 1 chunk = 1 khoản (khoan_so > 0) hoặc 1 điều (khoan_so = 0)
type Chunk struct {
	ID   string `json:"id"`
	Type string `json:"type"` // khoan | dieu

	// Hierarchy
	ChuongSo  int    `json:"chuong_so"`
	TenChuong string `json:"ten_chuong"`
	SoDieu    int    `json:"so_dieu"`
	TenDieu   string `json:"ten_dieu"`
	KhoanSo   int    `json:"khoan_so"` // 0 = dieu-level chunk

	NoiDung string `json:"noi_dung"`

	// Multi-law metadata v2
	LawID         string `json:"law_id"`
	LoaiVanBan    string `json:"loai_van_ban"`    // luat | nghi-dinh | thong-tu
	ThuTuUuTien   int    `json:"thu_tu_uu_tien"`  // 1=luat, 2=nd, 3=tt
	NgayHieuLuc   string `json:"ngay_hieu_luc"`
	ContextHeader string `json:"context_header"`  // "Luật Lao động 2012 > Chương III > Điều 37 > Khoản 1"
	ParentDieuID  string `json:"parent_dieu_id"`  // ID của điều cha

	TextForBM25      string `json:"text_for_bm25"`
	TextForEmbedding string `json:"text_for_embedding"`

	References []Reference `json:"references,omitempty"`
	Entities   []string    `json:"entities,omitempty"`

	// Legacy compat
	VanBanID string `json:"van_ban_id"`
	SoHieu   string `json:"so_hieu"`
}

type Edge struct {
	From     string  `json:"from"`
	To       string  `json:"to"`
	Relation string  `json:"relation"`
	Weight   float64 `json:"weight"`
}

type Output struct {
	ExtractedAt string   `json:"extracted_at"`
	Document    Document `json:"document"`
	Chunks      []Chunk  `json:"chunks"`
	GraphEdges  []Edge   `json:"graph_edges"`
}

// ════════════════════════════════════════════════════════════
// REGEX
// ════════════════════════════════════════════════════════════

var (
	reBlockTag = regexp.MustCompile(`(?i)<(?:br|p|div|tr|li|h[1-6]|table|thead|tbody|tfoot|/p|/div|/tr|/li|/table)[^>]*>`)
	reHTMLTag  = regexp.MustCompile(`<[^>]+>`)
	reHSpace   = regexp.MustCompile(`[ \t]+`)

	reSoHieu = regexp.MustCompile(`S[oố]:\s*([\d/A-Za-z.]+)`)
	reDate   = regexp.MustCompile(`ng[aà]y\s+(\d+)\s+th[aá]ng\s+(\d+)\s+n[aă]m\s+(\d+)`)
	reLoai   = regexp.MustCompile(`(B[Ộộ] LU[Ậậ]T|LU[Ậậ]T|NGH[Ịị] [ĐĐ][Ịị]NH|TH[Ôô]NG T[Ưư]|QUY[Ếế]T [ĐĐ][Ịị]NH)\s+([^\n<]{3,80})`)

	reChuong  = regexp.MustCompile(`(?i)ch[ươ][ơu]ng\s+((?:[IVXLCDM]+|[0-9]+))[.\s]+([^\n<]{3,120})`)
	reDieu    = regexp.MustCompile(`(?i)(?:điều|dieu)\s+(\d+)[.\s]+([^\n<]{2,120})`)
	reKhoan   = regexp.MustCompile(`^(\d+)\.\s+(.+)`)
	reDiem    = regexp.MustCompile(`^([a-zđ])\)\s+(.+)`)
	reRefDieu = regexp.MustCompile(`[Đđ]i[eề]u\s+(\d+)`)

	reRomanMap = map[string]int{
		"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5,
		"VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10,
		"XI": 11, "XII": 12, "XIII": 13, "XIV": 14, "XV": 15,
		"XVI": 16, "XVII": 17, "XVIII": 18, "XIX": 19, "XX": 20,
	}
)

// ════════════════════════════════════════════════════════════
// HELPERS
// ════════════════════════════════════════════════════════════

func stripHTML(s string) string {
	s = reBlockTag.ReplaceAllString(s, "\n")
	s = reHTMLTag.ReplaceAllString(s, "")
	s = strings.ReplaceAll(s, "&nbsp;", " ")
	s = strings.ReplaceAll(s, "&amp;", "&")
	s = strings.ReplaceAll(s, "&lt;", "<")
	s = strings.ReplaceAll(s, "&gt;", ">")
	s = strings.ReplaceAll(s, "&ldquo;", "\"")
	s = strings.ReplaceAll(s, "&rdquo;", "\"")
	return s
}

func cleanLine(s string) string {
	s = reHSpace.ReplaceAllString(s, " ")
	return strings.TrimSpace(s)
}

func parseLines(html string) []string {
	raw := stripHTML(html)
	lines := strings.Split(raw, "\n")
	var out []string
	for _, l := range lines {
		l = cleanLine(l)
		if l != "" {
			out = append(out, l)
		}
	}
	return out
}

func romanToInt(s string) int {
	s = strings.ToUpper(strings.TrimSpace(s))
	if v, ok := reRomanMap[s]; ok {
		return v
	}
	n, _ := strconv.Atoi(s)
	return n
}

// normalizeLoaiVanBan: normalize to slug
func normalizeLoaiVanBan(raw string) (string, int) {
	up := strings.ToUpper(raw)
	switch {
	case strings.Contains(up, "BỘ LUẬT") || strings.Contains(up, "BO LUAT"):
		return "luat", 1
	case strings.Contains(up, "LUẬT") || strings.Contains(up, "LUAT"):
		return "luat", 1
	case strings.Contains(up, "NGHỊ ĐỊNH") || strings.Contains(up, "NGHI DINH"):
		return "nghi-dinh", 2
	case strings.Contains(up, "THÔNG TƯ") || strings.Contains(up, "THONG TU"):
		return "thong-tu", 3
	case strings.Contains(up, "QUYẾT ĐỊNH") || strings.Contains(up, "QUYET DINH"):
		return "quyet-dinh", 3
	default:
		return "luat", 1
	}
}

// extractEntities: legal entity terms
func extractEntities(text string) []string {
	entityTerms := []string{
		"người lao động", "người sử dụng lao động", "hợp đồng lao động",
		"tổ chức công đoàn", "bảo hiểm xã hội", "bảo hiểm y tế",
		"bảo hiểm thất nghiệp", "tiền lương", "lương tối thiểu",
		"ngày nghỉ", "phép năm", "thai sản", "ốm đau", "tai nạn lao động",
		"đình công", "thử việc", "sa thải", "kỷ luật lao động",
	}
	var found []string
	lower := strings.ToLower(text)
	for _, term := range entityTerms {
		if strings.Contains(lower, term) {
			found = append(found, term)
		}
	}
	return found
}

// extractRefs: find Điều references
func extractRefs(text string, currentDieu int) []Reference {
	var refs []Reference
	matches := reRefDieu.FindAllStringSubmatch(text, -1)
	seen := map[int]bool{}
	for _, m := range matches {
		n, _ := strconv.Atoi(m[1])
		if n != currentDieu && n > 0 && !seen[n] {
			seen[n] = true
			idx := strings.Index(text, m[0])
			start := idx - 30
			if start < 0 { start = 0 }
			end := idx + len(m[0]) + 30
			if end > len(text) { end = len(text) }
			refs = append(refs, Reference{
				TargetDieu:   n,
				ContextSnip:  text[start:end],
				RelationType: "tham_chieu",
			})
		}
	}
	return refs
}

// ════════════════════════════════════════════════════════════
// PARSING
// ════════════════════════════════════════════════════════════

type parseState struct {
	chuongSo  int
	tenChuong string
	soDieu    int
	tenDieu   string
	dieuLines []string
}

func buildChunks(lines []string, doc Document, lawID string) ([]Chunk, []Edge) {
	var chunks []Chunk
	var edges []Edge

	state := parseState{}

	flushDieu := func() {
		if state.soDieu == 0 || len(state.dieuLines) == 0 {
			return
		}

		dieuID := fmt.Sprintf("%s_dieu_%03d", lawID, state.soDieu)
		body := strings.Join(state.dieuLines, "\n")

		// Parse khoản from body
		var khoans []Khoan
		var curKhoanLines []string
		var curKhoan *Khoan

		flushKhoan := func() {
			if curKhoan == nil { return }
			curKhoan.NoiDung = strings.Join(curKhoanLines, " ")
			khoans = append(khoans, *curKhoan)
			curKhoan = nil
			curKhoanLines = nil
		}

		for _, ln := range state.dieuLines {
			if m := reKhoan.FindStringSubmatch(ln); m != nil {
				flushKhoan()
				n, _ := strconv.Atoi(m[1])
				curKhoan = &Khoan{SoKhoan: n}
				curKhoanLines = []string{m[2]}
				// parse điểm
				// (điểm will be part of noí dung)
			} else if curKhoan != nil {
				curKhoanLines = append(curKhoanLines, ln)
			}
		}
		flushKhoan()

		contextHeader := fmt.Sprintf("%s > Chương %d > Điều %d", doc.TenVanBan, state.chuongSo, state.soDieu)

		if len(khoans) == 0 {
			// Emit điều-level chunk
			textBM25 := fmt.Sprintf("%s Điều %d %s Chương %d %s %s",
				doc.TenVanBan, state.soDieu, state.tenDieu, state.chuongSo, state.tenChuong, body)
			textEmbed := fmt.Sprintf("passage: %s - Chương %d: %s - Điều %d. %s\n%s",
				doc.TenVanBan, state.chuongSo, state.tenChuong, state.soDieu, state.tenDieu, body)

			c := Chunk{
				ID:            dieuID,
				Type:          "dieu",
				ChuongSo:      state.chuongSo,
				TenChuong:     state.tenChuong,
				SoDieu:        state.soDieu,
				TenDieu:       state.tenDieu,
				KhoanSo:       0,
				NoiDung:       body,
				LawID:         lawID,
				LoaiVanBan:    doc.LoaiVanBan,
				ThuTuUuTien:   doc.ThuTuUuTien,
				NgayHieuLuc:   doc.NgayHieuLuc,
				ContextHeader: contextHeader,
				ParentDieuID:  "",
				TextForBM25:   textBM25,
				TextForEmbedding: textEmbed,
				References:    extractRefs(body, state.soDieu),
				Entities:      extractEntities(body),
				VanBanID:      doc.ID,
				SoHieu:        doc.SoHieu,
			}
			chunks = append(chunks, c)
		} else {
			// Emit khoản-level chunks (1 chunk = 1 khoản)
			for _, k := range khoans {
				khoanID := fmt.Sprintf("%s_dieu_%03d_khoan_%d", lawID, state.soDieu, k.SoKhoan)
				ctxHeader := fmt.Sprintf("%s > Chương %d > Điều %d > Khoản %d",
					doc.TenVanBan, state.chuongSo, state.soDieu, k.SoKhoan)
				textBM25 := fmt.Sprintf("%s Điều %d %s Khoản %d %s Chương %d %s",
					doc.TenVanBan, state.soDieu, state.tenDieu, k.SoKhoan, k.NoiDung, state.chuongSo, state.tenChuong)
				textEmbed := fmt.Sprintf("passage: %s - Chương %d: %s - Điều %d. %s - Khoản %d\n%s",
					doc.TenVanBan, state.chuongSo, state.tenChuong, state.soDieu, state.tenDieu, k.SoKhoan, k.NoiDung)

				c := Chunk{
					ID:               khoanID,
					Type:             "khoan",
					ChuongSo:         state.chuongSo,
					TenChuong:        state.tenChuong,
					SoDieu:           state.soDieu,
					TenDieu:          state.tenDieu,
					KhoanSo:          k.SoKhoan,
					NoiDung:          k.NoiDung,
					LawID:            lawID,
					LoaiVanBan:       doc.LoaiVanBan,
					ThuTuUuTien:      doc.ThuTuUuTien,
					NgayHieuLuc:      doc.NgayHieuLuc,
					ContextHeader:    ctxHeader,
					ParentDieuID:     dieuID,
					TextForBM25:      textBM25,
					TextForEmbedding: textEmbed,
					References:       extractRefs(k.NoiDung, state.soDieu),
					Entities:         extractEntities(k.NoiDung),
					VanBanID:         doc.ID,
					SoHieu:           doc.SoHieu,
				}
				chunks = append(chunks, c)

				// Graph edge: khoan → dieu
				edges = append(edges, Edge{
					From:     khoanID,
					To:       dieuID,
					Relation: "thuoc_dieu",
					Weight:   1.0,
				})
			}

			// Also emit dieu-level summary for fallback
			textBM25 := fmt.Sprintf("%s Điều %d %s Chương %d %s %s",
				doc.TenVanBan, state.soDieu, state.tenDieu, state.chuongSo, state.tenChuong, body)
			textEmbed := fmt.Sprintf("passage: %s - Chương %d: %s - Điều %d. %s\n%s",
				doc.TenVanBan, state.chuongSo, state.tenChuong, state.soDieu, state.tenDieu, body)

			dieuChunk := Chunk{
				ID:               dieuID,
				Type:             "dieu",
				ChuongSo:         state.chuongSo,
				TenChuong:        state.tenChuong,
				SoDieu:           state.soDieu,
				TenDieu:          state.tenDieu,
				KhoanSo:          0,
				NoiDung:          body,
				LawID:            lawID,
				LoaiVanBan:       doc.LoaiVanBan,
				ThuTuUuTien:      doc.ThuTuUuTien,
				NgayHieuLuc:      doc.NgayHieuLuc,
				ContextHeader:    contextHeader,
				ParentDieuID:     "",
				TextForBM25:      textBM25,
				TextForEmbedding: textEmbed,
				References:       extractRefs(body, state.soDieu),
				Entities:         extractEntities(body),
				VanBanID:         doc.ID,
				SoHieu:           doc.SoHieu,
			}
			chunks = append(chunks, dieuChunk)
		}

		// Graph edges between references
		for _, c := range chunks {
			if c.SoDieu == state.soDieu {
				for _, ref := range c.References {
					edges = append(edges, Edge{
						From:     c.ID,
						To:       fmt.Sprintf("%s_dieu_%03d", lawID, ref.TargetDieu),
						Relation: ref.RelationType,
						Weight:   0.8,
					})
				}
			}
		}
	}

	for _, line := range lines {
		// Check Chương
		if m := reChuong.FindStringSubmatch(line); m != nil {
			flushDieu()
			state.chuongSo = romanToInt(m[1])
			state.tenChuong = strings.TrimSpace(m[2])
			state.soDieu = 0
			state.tenDieu = ""
			state.dieuLines = nil
			continue
		}

		// Check Điều
		if m := reDieu.FindStringSubmatch(line); m != nil {
			flushDieu()
			n, _ := strconv.Atoi(m[1])
			state.soDieu = n
			state.tenDieu = strings.TrimSpace(m[2])
			state.dieuLines = nil
			continue
		}

		// Collect body lines
		if state.soDieu > 0 {
			state.dieuLines = append(state.dieuLines, line)
		}
	}

	flushDieu()
	return chunks, edges
}

// ════════════════════════════════════════════════════════════
// DOCUMENT METADATA EXTRACTION
// ════════════════════════════════════════════════════════════

func extractDocMeta(lines []string) Document {
	var doc Document
	text := strings.Join(lines[:min(len(lines), 100)], " ")

	if m := reSoHieu.FindStringSubmatch(text); m != nil {
		doc.SoHieu = m[1]
		doc.ID = strings.ReplaceAll(strings.ToLower(m[1]), "/", ".")
	}

	if m := reDate.FindStringSubmatch(text); m != nil {
		doc.NgayBanHanh = fmt.Sprintf("%s/%s/%s", m[1], m[2], m[3])
	}

	if m := reLoai.FindStringSubmatch(text); m != nil {
		raw := m[1]
		loai, priority := normalizeLoaiVanBan(raw)
		doc.LoaiVanBan = loai
		doc.ThuTuUuTien = priority
		doc.TenVanBan = strings.TrimSpace(m[0])
	} else {
		doc.LoaiVanBan = "luat"
		doc.ThuTuUuTien = 1
	}

	return doc
}

func min(a, b int) int {
	if a < b { return a }
	return b
}

// ════════════════════════════════════════════════════════════
// MAIN
// ════════════════════════════════════════════════════════════

func main() {
	var (
		inputFile  string
		outputFile string
		lawID      string
		ngayHieuLuc string
	)
	flag.StringVar(&inputFile, "file", "", "HTML input file")
	flag.StringVar(&outputFile, "output", "", "JSON output file")
	flag.StringVar(&lawID, "law-id", "unknown", "Law slug (e.g. lao-dong, bhxh)")
	flag.StringVar(&ngayHieuLuc, "hieu-luc", "", "Ngày hiệu lực (YYYY-MM-DD)")
	flag.Parse()

	// Read input
	var htmlBytes []byte
	var err error
	if inputFile != "" {
		htmlBytes, err = os.ReadFile(inputFile)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Cannot read file: %v\n", err)
			os.Exit(1)
		}
	} else {
		htmlBytes, err = io.ReadAll(os.Stdin)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Cannot read stdin: %v\n", err)
			os.Exit(1)
		}
	}

	lines := parseLines(string(htmlBytes))
	doc := extractDocMeta(lines)
	doc.LawID = lawID
	doc.NgayHieuLuc = ngayHieuLuc
	if doc.SoHieu == "" {
		doc.SoHieu = lawID
		doc.ID = lawID
	}

	chunks, edges := buildChunks(lines, doc, lawID)

	// Count stats
	dieuCount := 0
	for _, c := range chunks {
		if c.Type == "dieu" { dieuCount++ }
	}
	doc.TongSoDieu = dieuCount

	out := Output{
		ExtractedAt: time.Now().Format(time.RFC3339),
		Document:    doc,
		Chunks:      chunks,
		GraphEdges:  edges,
	}

	data, err := json.MarshalIndent(out, "", "  ")
	if err != nil {
		fmt.Fprintf(os.Stderr, "JSON encode error: %v\n", err)
		os.Exit(1)
	}

	if outputFile != "" {
		if err := os.WriteFile(outputFile, data, 0644); err != nil {
			fmt.Fprintf(os.Stderr, "Write error: %v\n", err)
			os.Exit(1)
		}
		// Stats to stderr
		khoanCount := len(chunks) - dieuCount
		fmt.Fprintf(os.Stderr, "✅ Extracted: %d điều → %d khoản chunks (law_id=%s, loai=%s)\n",
			dieuCount, khoanCount, lawID, doc.LoaiVanBan)
	} else {
		fmt.Println(string(data))
	}
}
