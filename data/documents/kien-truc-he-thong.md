# Kiến trúc hệ thống RAG nội bộ

## Tổng quan các tầng

Hệ thống được chia thành bốn tầng tách biệt: tầng tiếp nhận (API), tầng điều phối
(orchestrator), tầng adaptor, và tầng hạ tầng. Mỗi tầng chỉ được phép biết đến tầng
ngay dưới nó thông qua một giao diện trừu tượng, không bao giờ gọi thẳng vào lớp cài
đặt cụ thể. Nguyên tắc này nghe có vẻ hình thức nhưng nó là thứ cho phép đổi nhà cung
cấp mô hình ngôn ngữ mà không phải sửa một dòng nào trong tầng điều phối.

## Vì sao tầng adaptor tồn tại

Tầng adaptor định nghĩa ba giao thức: nhà cung cấp embedding, kho vector, và nhà cung
cấp mô hình ngôn ngữ. Chúng được khai báo dưới dạng giao thức cấu trúc chứ không phải
lớp cơ sở để kế thừa. Khác biệt này quan trọng: một lớp mới chỉ cần có đúng hình dạng
phương thức là dùng được ngay, không phải import bất cứ thứ gì từ tầng adaptor, nên
không tạo ra phụ thuộc ngược.

Hệ quả thực tế là khi thêm một nhà cung cấp mới, ta viết một lớp mới và thêm một nhánh
trong nhà máy khởi tạo. Tầng điều phối, tầng API và toàn bộ bộ kiểm thử không đổi.

## Luồng xử lý câu hỏi

Khi một câu hỏi đi vào, hệ thống thực hiện theo thứ tự: sinh vector cho câu hỏi hiện
tại, tìm kiếm trong kho vector, kiểm tra kết quả rỗng, dựng thông điệp có ngữ cảnh, rồi
gọi mô hình ngôn ngữ sinh câu trả lời.

Bước kiểm tra kết quả rỗng là một trong hai lớp chống bịa đặt của hệ thống. Nếu kho
vector không trả về đoạn văn nào vượt ngưỡng điểm, hệ thống trả lời từ chối ngay lập
tức mà không gọi mô hình ngôn ngữ. Điều này vừa tiết kiệm chi phí vừa loại bỏ khả năng
mô hình tự bịa ra câu trả lời từ kiến thức nền của nó.

Lớp chống bịa thứ hai là ngưỡng điểm tương đồng. Đoạn văn có điểm thấp hơn ngưỡng sẽ bị
loại trước khi tới tay mô hình ngôn ngữ.

## Chiến lược chia đoạn văn bản

Tài liệu dài được cắt thành các đoạn nhỏ trước khi sinh vector. Kích thước đoạn mặc
định là một nghìn ký tự, và các đoạn liền nhau có phần chồng lấn để một câu bị cắt
ngang vẫn xuất hiện trọn vẹn ở ít nhất một đoạn.

Với tệp Markdown, bộ chia đoạn bám theo cấu trúc tiêu đề thay vì cắt mù theo số ký tự.
Mỗi đoạn được gán tiêu đề của mục chứa nó, và thông tin này đi kèm vào phần dữ liệu bổ
trợ của điểm vector. Nhờ vậy khi trả kết quả, hệ thống nói được đoạn văn thuộc mục nào
chứ không chỉ thuộc tệp nào.

Đoạn quá ngắn sẽ bị loại bỏ. Một tiêu đề không có nội dung theo sau không tạo ra đoạn
nào, vì nhúng một dòng tiêu đề trơ trọi chỉ sinh ra nhiễu trong không gian vector.

## Tính bất biến của việc nạp lại

Việc nạp tài liệu được thiết kế để chạy lại nhiều lần cho cùng kết quả. Định danh của
mỗi điểm vector được sinh tất định từ tên nguồn và số thứ tự đoạn, và toàn bộ điểm cũ
của một nguồn bị xoá trước khi ghi điểm mới.

Hai cơ chế này kết hợp lại cho phép sửa một tài liệu rồi nạp lại mà không tạo bản sao
trùng lặp, đồng thời không để sót đoạn cũ khi tài liệu mới ngắn hơn tài liệu cũ.

## Cấu hình và thứ tự ưu tiên

Cấu hình được nạp theo thứ tự ưu tiên giảm dần: tham số truyền thẳng vào hàm khởi tạo,
biến môi trường, tệp môi trường cục bộ, tệp cấu hình dạng YAML, và cuối cùng là giá trị
mặc định khai báo trong mã nguồn. Trường lồng nhau dùng dấu gạch dưới đôi để phân cấp.

Không được thêm một cơ chế đọc cấu hình thứ hai chạy song song với thứ tự này. Hai
nguồn cấu hình cạnh tranh nhau là loại lỗi mà người vận hành mất hàng giờ mới lần ra.
