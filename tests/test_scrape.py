import unittest
from unittest.mock import patch, MagicMock, mock_open
from datetime import date

from swlwi.scrape import (
    ListIssues,
    Issue,
    Article,
    ExtractArticles,
    FetchArticle,
    SaveArticle,
    SkipExistingIssues,
    ExtractArticleContent,
    _extract_domain_from_url,
)


class TestListIssues(unittest.TestCase):
    @patch("requests.get")
    def test_process(self, mock_get):
        # Mock the HTML content
        html_content = """
        <div class="table-issue">
            <p class="title-table-issue"><a href="/issues/1">Issue 1</a></p>
            <p class="text-table-issue">1st October 2023</p>
        </div>
        <div class="table-issue">
            <p class="title-table-issue"><a href="/issues/2">Issue 2</a></p>
            <p class="text-table-issue">2nd October 2023</p>
        </div>
        """

        # Mock the response object
        mock_response = MagicMock()
        mock_response.content = html_content
        mock_get.return_value = mock_response

        # Create an instance of ListIssues
        list_issues = ListIssues(id="List Issues")

        # Mock the send method to capture the output
        list_issues.send = MagicMock()

        # Call the process method
        list_issues.process("http://example.com/issues/", 0)

        # Check that the send method was called twice
        self.assertEqual(2, list_issues.send.call_count)

        # Check the arguments of the first call
        first_call_args = list_issues.send.call_args_list[0][0]
        self.assertEqual("issue", first_call_args[0])
        self.assertIsInstance(first_call_args[1], Issue)
        self.assertEqual(1, first_call_args[1].num)
        self.assertEqual("http://example.com/issues/1", first_call_args[1].url)
        self.assertEqual(date(2023, 10, 1), first_call_args[1].date)
        self.assertEqual((0, 2), first_call_args[1].item_of)

        # Check the arguments of the second call
        second_call_args = list_issues.send.call_args_list[1][0]
        self.assertEqual("issue", second_call_args[0])
        self.assertIsInstance(second_call_args[1], Issue)
        self.assertEqual(2, second_call_args[1].num)
        self.assertEqual("http://example.com/issues/2", second_call_args[1].url)
        self.assertEqual(date(2023, 10, 2), second_call_args[1].date)
        self.assertEqual((1, 2), second_call_args[1].item_of)


class TestSkipExistingIssues(unittest.TestCase):
    @patch("os.path.exists")
    def test_process(self, mock_exists):
        # Define test cases
        test_cases = [
            {
                "name": "force_all_true",
                "issue_num": 1,
                "path": "/fake/path",
                "force_all": True,
                "issue_exists": False,
                "expected_send_called": True,
            },
            {
                "name": "issue_does_not_exist",
                "issue_num": 2,
                "path": "/fake/path",
                "force_all": False,
                "issue_exists": False,
                "expected_send_called": True,
            },
            {
                "name": "issue_exists",
                "issue_num": 3,
                "path": "/fake/path",
                "force_all": False,
                "issue_exists": True,
                "expected_send_called": False,
            },
        ]

        for case in test_cases:
            with self.subTest(case=case["name"]):
                # Set up the mock to return the appropriate value
                mock_exists.return_value = case["issue_exists"]

                # Create an instance of SkipExistingIssues
                skip_existing_issues = SkipExistingIssues(id="Skip Existing Issues")

                # Mock the send method to capture the output
                skip_existing_issues.send = MagicMock()

                # Create a mock Issue object
                mock_issue = Issue(
                    num=case["issue_num"], url="http://example.com", date=date(2024, 1, 1), item_of=(0, 1)
                )

                # Call the process method
                skip_existing_issues.process(issue=mock_issue, path=case["path"], force_all=case["force_all"])

                # Check if the send method was called or not
                if case["expected_send_called"]:
                    skip_existing_issues.send.assert_called_once_with("issue", mock_issue)
                else:
                    skip_existing_issues.send.assert_not_called()

                # Reset the mock for the next iteration
                skip_existing_issues.send.reset_mock()


class TestExtractArticles(unittest.TestCase):
    @patch("requests.get")
    def test_process(self, mock_get):
        # Example HTML content
        example_html = """
        <a href="/" class="nuxt-link-active" data-v-6453ed57><img src="/img/SWLW_Logo-33.svg" alt="Software Lead Weekly" data-v-6453ed57></a></h1></div></div> <div class="container-snow-header" data-v-0320d9e7><img src="/img/snow-07.svg" alt data-v-0320d9e7></div> <div class="sub-header" data-v-0320d9e7><div class="container" data-v-0320d9e7><div class="row justify-content-center" data-v-0320d9e7><div class="col-12 col-sm-8 col-md-7 mb-2 mb-sm-0 col-xl-6" data-v-0320d9e7><p class="sub-header-text" data-v-0320d9e7><span data-v-0320d9e7>Issue #613, 23rd August 2024</span></p></div> <div class="col-12 col-sm-4 col-lg-2" data-v-0320d9e7><div class="button-archive" data-v-0320d9e7><a href="/issues/" class="nuxt-link-active" data-v-0320d9e7><svg aria-hidden="true" focusable="false" data-prefix="fas" data-icon="archive" role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" class="svg-inline--fa fa-archive fa-w-16" style="height:14px;margin-right:6px;vertical-align:baseline" data-v-0320d9e7><path fill="currentColor" d="M32 448c0 17.7 14.3 32 32 32h384c17.7 0 32-14.3 32-32V160H32v288zm160-212c0-6.6 5.4-12 12-12h104c6.6 0 12 5.4 12 12v8c0 6.6-5.4 12-12 12H204c-6.6 0-12-5.4-12-12v-8zM480 32H32C14.3 32 0 46.3 0 64v48c0 8.8 7.2 16 16 16h480c8.8 0 16-7.2 16-16V64c0-17.7-14.3-32-32-32z" data-v-0320d9e7></path></svg>ARCHIVE
                      </a></div></div></div></div></div></header> <div class="container mt-4" data-v-0320d9e7><div class="row justify-content-center" data-v-0320d9e7><div class="col-12 col-md-11 col-lg-9 col-xl-8" data-v-0320d9e7><h3 class="topic-title" data-v-0320d9e7>This Week"s Favorite</h3> <hr data-v-0320d9e7> <div data-v-0320d9e7><a href="https://www.rkg.blog/demanding.php" title="https://www.rkg.blog/demanding.php" data-url="https://www.rkg.blog/demanding.php" class="post-title" data-v-0320d9e7>Demanding and Supportive</a> <br data-v-0320d9e7>3 minutes read.<br data-v-0320d9e7><br data-v-0320d9e7>
                  "Most people think of demanding and supportive as opposite ends of a spectrum. You can either be tough or you can be nice. But the best leaders don’t choose. They are both highly demanding and highly supportive. They push you to new heights and they also have your back. What I’ve come to realize over time is that, far from being contradictory, being demanding and supportive are inextricably linked. It’s the way you are when you believe in someone more than they believe in themselves." -- Ravi Gupta wrote it so beautifully. Many of us want to be both demanding and supportive. To our family, to our friends, to our teammates, but above all and before all - to ourselves.
                  <br data-v-0320d9e7><br data-v-0320d9e7><b data-v-0320d9e7>Read</b> it later via
                  <a href="https://getpocket.com/save?url=https://www.rkg.blog/demanding.php&title=Demanding%20and%20Supportive" target="_blank" data-v-7f52ad97 data-v-0320d9e7>Pocket</a>
                  or
                  <a href="http://www.instapaper.com/hello2?url=https://www.rkg.blog/demanding.php&title=Demanding%20and%20Supportive" target="_blank" data-v-763e09c6 data-v-0320d9e7>Instapaper</a>. <br data-v-0320d9e7><b data-v-0320d9e7>
                    Share</b>
                  it via
                  <a href="http://twitter.com/share?text=%22Most%20people%20think%20of%20demanding%20and%20supportive%20as%20opposite%20ends%20of%20a%20spectrum.%20You%20can%20either%20be%20tough%20or%20you%20can%20be%20nice.%20But%20the%20best%20leaders%20don%E2%80%99t%20choose.%20They%20are%20both%20highly%20demanding%20and%20highly%20supportive.%20They%20push%20you%20to%20new%20heights%20and%20they%20also%20have%20your%20back.%20What%20I%E2%80%99ve%20come%20to%20realize%20over%20time%20is%20that,%20far%20from%20being%20contradictory,%20being%20demanding%20and%20supportive%20are%20inextricably%20linked.%20It%E2%80%99s%20the%20way%20you%20are%20when%20you%20believe%20in%20someone%20more%20than%20they%20believe%20in%20themselves.%22%20--%20Ravi%20Gupta%20wrote%20it%20so%20beautifully.%20Many%20of%20us%20want%20to%20be%20both%20demanding%20and%20supportive.%20To%20our%20family,%20to%20our%20friends,%20to%20our%20teammates,%20but%20above%20all%20and%20before%20all%20-%20to%20ourselves.&url=https://www.rkg.blog/demanding.php&via=orenellenbogen" target="_blank" data-v-727fa118 data-v-0320d9e7>Twitter</a>
                  or
                  <a href="mailto:?subject=Demanding%20and%20Supportive&body=Great post: https://www.rkg.blog/demanding.php Found it via http://softwareleadweekly.com/" target="_blank" data-v-508ac71a data-v-0320d9e7>email</a>.
                  <br data-v-0320d9e7><br data-v-0320d9e7><br data-v-0320d9e7></div></div></div><div class="row justify-content-center" data-v-0320d9e7><div class="col-12 col-md-11 col-lg-9 col-xl-8" data-v-0320d9e7><h3 class="topic-title" data-v-0320d9e7>Culture</h3> <hr data-v-0320d9e7> <div data-v-0320d9e7><a href="https://x.com/carlvellotti/status/1821584562817736935" title="https://x.com/carlvellotti/status/1821584562817736935" data-url="https://x.com/carlvellotti/status/1821584562817736935" class="post-title" data-v-0320d9e7>"Did You Finish Writing That PRD?"</a> <br data-v-0320d9e7>1 minutes read.<br data-v-0320d9e7><br data-v-0320d9e7>
                  My humble effort to help you start the weekend with a smile on your face.
                  <br data-v-0320d9e7><br data-v-0320d9e7><b data-v-0320d9e7>Read</b> it later via
                  <a href="https://getpocket.com/save?url=https://x.com/carlvellotti/status/1821584562817736935&title=%22Did%20You%20Finish%20Writing%20That%20PRD?%22" target="_blank" data-v-7f52ad97 data-v-0320d9e7>Pocket</a>
                  or
                  <a href="http://www.instapaper.com/hello2?url=https://x.com/carlvellotti/status/1821584562817736935&title=%22Did%20You%20Finish%20Writing%20That%20PRD?%22" target="_blank" data-v-763e09c6 data-v-0320d9e7>Instapaper</a>. <br data-v-0320d9e7><b data-v-0320d9e7>
                    Share</b>
                  it via
                  <a href="http://twitter.com/share?text=My%20humble%20effort%20to%20help%20you%20start%20the%20weekend%20with%20a%20smile%20on%20your%20face.&url=https://x.com/carlvellotti/status/1821584562817736935&via=orenellenbogen" target="_blank" data-v-727fa118 data-v-0320d9e7>Twitter</a>
                  or
                  <a href="mailto:?subject=%22Did%20You%20Finish%20Writing%20That%20PRD?%22&body=Great post: https://x.com/carlvellotti/status/1821584562817736935 Found it via http://softwareleadweekly.com/" target="_blank" data-v-508ac71a data-v-0320d9e7>email</a>.
                  <br data-v-0320d9e7><br data-v-0320d9e7><br data-v-0320d9e7></div><div data-v-0320d9e7><a href="https://maruz.medium.com/the-map-is-not-the-territory-6b8bb6d86973" title="https://maruz.medium.com/the-map-is-not-the-territory-6b8bb6d86973" data-url="https://maruz.medium.com/the-map-is-not-the-territory-6b8bb6d86973" class="post-title" data-v-0320d9e7>The Map Is Not the Territory</a> <br data-v-0320d9e7>9 minutes read.<br data-v-0320d9e7><br data-v-0320d9e7>
                  Mario Caropreso is spot on with his observation: "In order to ensure Operational Excellence is prioritised, it is important to create a relentless focus on the customer. In a healthy engineering team, the starting point should always be the customer. [...] The problem is that usually the customer is exactly the person whose voice is missing when this question is asked, thus it’s important to find ways to represent the customer’s point of view in these discussions."
                  <br data-v-0320d9e7><br data-v-0320d9e7><b data-v-0320d9e7>Read</b> it later via
                  <a href="https://getpocket.com/save?url=https://maruz.medium.com/the-map-is-not-the-territory-6b8bb6d86973&title=The%20Map%20Is%20Not%20the%20Territory" target="_blank" data-v-7f52ad97 data-v-0320d9e7>Pocket</a>
                  or
                  <a href="http://www.instapaper.com/hello2?url=https://maruz.medium.com/the-map-is-not-the-territory-6b8bb6d86973&title=The%20Map%20Is%20Not%20the%20Territory" target="_blank" data-v-763e09c6 data-v-0320d9e7>Instapaper</a>. <br data-v-0320d9e7><b data-v-0320d9e7>
                    Share</b>
                  it via
                  <a href="http://twitter.com/share?text=Mario%20Caropreso%20is%20spot%20on%20with%20his%20observation:%20%22In%20order%20to%20ensure%20Operational%20Excellence%20is%20prioritised,%20it%20is%20important%20to%20create%20a%20relentless%20focus%20on%20the%20customer.%20In%20a%20healthy%20engineering%20team,%20the%20starting%20point%20should%20always%20be%20the%20customer.%20%5B...%5D%20The%20problem%20is%20that%20usually%20the%20customer%20is%20exactly%20the%20person%20whose%20voice%20is%20missing%20when%20this%20question%20is%20asked,%20thus%20it%E2%80%99s%20important%20to%20find%20ways%20to%20represent%20the%20customer%E2%80%99s%20point%20of%20view%20in%20these%20discussions.%22&url=https://maruz.medium.com/the-map-is-not-the-territory-6b8bb6d86973&via=orenellenbogen" target="_blank" data-v-727fa118 data-v-0320d9e7>Twitter</a>
                  or
                  <a href="mailto:?subject=The%20Map%20Is%20Not%20the%20Territory&body=Great post: https://maruz.medium.com/the-map-is-not-the-territory-6b8bb6d86973 Found it via http://softwareleadweekly.com/" target="_blank" data-v-508ac71a data-v-0320d9e7>email</a>.
                  <br data-v-0320d9e7><br data-v-0320d9e7><br data-v-0320d9e7></div><div data-v-0320d9e7><a href="https://cremich.cloud/building-with-purpose" title="https://cremich.cloud/building-with-purpose" data-url="https://cremich.cloud/building-with-purpose" class="post-title" data-v-0320d9e7>Building With Purpose: How to Explain Developers That They Are Wasting Company Money</a> <br data-v-0320d9e7>5 minutes read.<br data-v-0320d9e7><br data-v-0320d9e7>
                  Asking the question of how success would look like, in metrics or otherwise, can be a great way to align people on the outcome everyone seeks to experience. Once you have a few ways to explain how success looks like, try to offer painful tradeoffs to see which are more valuable to the stakeholders and the business. To counter the automatic reaction of bloated planning, I find it helpful to use a time constraint (e.g. "we'll use the next 2 days to complete alignment and set goals and tradeoffs").
                  <br data-v-0320d9e7><br data-v-0320d9e7><b data-v-0320d9e7>Read</b> it later via
                  <a href="https://getpocket.com/save?url=https://cremich.cloud/building-with-purpose&title=Building%20With%20Purpose:%20How%20to%20Explain%20Developers%20That%20They%20Are%20Wasting%20Company%20Money" target="_blank" data-v-7f52ad97 data-v-0320d9e7>Pocket</a>
                  or
                  <a href="http://www.instapaper.com/hello2?url=https://cremich.cloud/building-with-purpose&title=Building%20With%20Purpose:%20How%20to%20Explain%20Developers%20That%20They%20Are%20Wasting%20Company%20Money" target="_blank" data-v-763e09c6 data-v-0320d9e7>Instapaper</a>. <br data-v-0320d9e7><b data-v-0320d9e7>
                    Share</b>
                  it via
                  <a href="http://twitter.com/share?text=Asking%20the%20question%20of%20how%20success%20would%20look%20like,%20in%20metrics%20or%20otherwise,%20can%20be%20a%20great%20way%20to%20align%20people%20on%20the%20outcome%20everyone%20seeks%20to%20experience.%20Once%20you%20have%20a%20few%20ways%20to%20explain%20how%20success%20looks%20like,%20try%20to%20offer%20painful%20tradeoffs%20to%20see%20which%20are%20more%20valuable%20to%20the%20stakeholders%20and%20the%20business.%20To%20counter%20the%20automatic%20reaction%20of%20bloated%20planning,%20I%20find%20it%20helpful%20to%20use%20a%20time%20constraint%20(e.g.%20%22we"ll%20use%20the%20next%202%20days%20to%20complete%20alignment%20and%20set%20goals%20and%20tradeoffs%22).&url=https://cremich.cloud/building-with-purpose&via=orenellenbogen" target="_blank" data-v-727fa118 data-v-0320d9e7>Twitter</a>
                  or
                  <a href="mailto:?subject=Building%20With%20Purpose:%20How%20to%20Explain%20Developers%20That%20They%20Are%20Wasting%20Company%20Money&body=Great post: https://cremich.cloud/building-with-purpose Found it via http://softwareleadweekly.com/" target="_blank" data-v-508ac71a data-v-0320d9e7>email</a>.
                  <br data-v-0320d9e7><br data-v-0320d9e7><br data-v-0320d9e7></div><div data-v-0320d9e7><a href="https://marcgg.com/blog/2021/03/27/one-on-one-format/" title="https://marcgg.com/blog/2021/03/27/one-on-one-format/" data-url="https://marcgg.com/blog/2021/03/27/one-on-one-format/" class="post-title" data-v-0320d9e7>One on One Meeting Format Ideas</a> <br data-v-0320d9e7>6 minutes read.<br data-v-0320d9e7><br data-v-0320d9e7>
                  This is an excellent post for managers who seek ways to have effective 1:1s with their teammates, going beyond the obvious project status update that doesn't help to build deeper relationships.
                  <br data-v-0320d9e7><br data-v-0320d9e7><b data-v-0320d9e7>Read</b> it later via
                  <a href="https://getpocket.com/save?url=https://marcgg.com/blog/2021/03/27/one-on-one-format/&title=One%20on%20One%20Meeting%20Format%20Ideas" target="_blank" data-v-7f52ad97 data-v-0320d9e7>Pocket</a>
                  or
                  <a href="http://www.instapaper.com/hello2?url=https://marcgg.com/blog/2021/03/27/one-on-one-format/&title=One%20on%20One%20Meeting%20Format%20Ideas" target="_blank" data-v-763e09c6 data-v-0320d9e7>Instapaper</a>. <br data-v-0320d9e7><b data-v-0320d9e7>
                    Share</b>
                  it via
                  <a href="http://twitter.com/share?text=This%20is%20an%20excellent%20post%20for%20managers%20who%20seek%20ways%20to%20have%20effective%201:1s%20with%20their%20teammates,%20going%20beyond%20the%20obvious%20project%20status%20update%20that%20doesn"t%20help%20to%20build%20deeper%20relationships.&url=https://marcgg.com/blog/2021/03/27/one-on-one-format/&via=orenellenbogen" target="_blank" data-v-727fa118 data-v-0320d9e7>Twitter</a>
                  or
                  <a href="mailto:?subject=One%20on%20One%20Meeting%20Format%20Ideas&body=Great post: https://marcgg.com/blog/2021/03/27/one-on-one-format/ Found it via http://softwareleadweekly.com/" target="_blank" data-v-508ac71a data-v-0320d9e7>email</a>.
                  <br data-v-0320d9e7><br data-v-0320d9e7><br data-v-0320d9e7></div></div></div><div class="row justify-content-center" data-v-0320d9e7><div class="col-12 col-md-11 col-lg-9 col-xl-8" data-v-0320d9e7><h3 class="topic-title" data-v-0320d9e7>Peopleware</h3> <hr data-v-0320d9e7> <div data-v-0320d9e7><a href="https://read.perspectiveship.com/p/circle-of-competence" title="https://read.perspectiveship.com/p/circle-of-competence" data-url="https://read.perspectiveship.com/p/circle-of-competence" class="post-title" data-v-0320d9e7>Circle of Competence - Mental Model</a> <br data-v-0320d9e7>4 minutes read.<br data-v-0320d9e7><br data-v-0320d9e7>
                  The Circle of Competence idea can be a powerful method to extract both feedback and insights from your peers and managers (across levels). It will help map out how the organization sees you, where they think your strength is, and how you can increase it if that's something you wish to achieve. So next time you have a 1:1 or meeting with someone you trust, ask them: "What do you think looks easy for me to do quickly and with excellent quality that others usually struggle with?"
                  <br data-v-0320d9e7><br data-v-0320d9e7><b data-v-0320d9e7>Read</b> it later via
                  <a href="https://getpocket.com/save?url=https://read.perspectiveship.com/p/circle-of-competence&title=Circle%20of%20Competence%20-%20Mental%20Model" target="_blank" data-v-7f52ad97 data-v-0320d9e7>Pocket</a>
                  or
                  <a href="http://www.instapaper.com/hello2?url=https://read.perspectiveship.com/p/circle-of-competence&title=Circle%20of%20Competence%20-%20Mental%20Model" target="_blank" data-v-763e09c6 data-v-0320d9e7>Instapaper</a>. <br data-v-0320d9e7><b data-v-0320d9e7>
                    Share</b>
                  it via
                  <a href="http://twitter.com/share?text=The%20Circle%20of%20Competence%20idea%20can%20be%20a%20powerful%20method%20to%20extract%20both%20feedback%20and%20insights%20from%20your%20peers%20and%20managers%20(across%20levels).%20It%20will%20help%20map%20out%20how%20the%20organization%20sees%20you,%20where%20they%20think%20your%20strength%20is,%20and%20how%20you%20can%20increase%20it%20if%20that"s%20something%20you%20wish%20to%20achieve.%20So%20next%20time%20you%20have%20a%201:1%20or%20meeting%20with%20someone%20you%20trust,%20ask%20them:%20%22What%20do%20you%20think%20looks%20easy%20for%20me%20to%20do%20quickly%20and%20with%20excellent%20quality%20that%20others%20usually%20struggle%20with?%22&url=https://read.perspectiveship.com/p/circle-of-competence&via=orenellenbogen" target="_blank" data-v-727fa118 data-v-0320d9e7>Twitter</a>
                  or
                  <a href="mailto:?subject=Circle%20of%20Competence%20-%20Mental%20Model&body=Great post: https://read.perspectiveship.com/p/circle-of-competence Found it via http://softwareleadweekly.com/" target="_blank" data-v-508ac71a data-v-0320d9e7>email</a>.
                  <br data-v-0320d9e7><br data-v-0320d9e7><br data-v-0320d9e7></div><div data-v-0320d9e7><a href="https://medium.com/@rrpinc/priorities-of-a-great-engineering-leader-9bba11bd005d" title="https://medium.com/@rrpinc/priorities-of-a-great-engineering-leader-9bba11bd005d" data-url="https://medium.com/@rrpinc/priorities-of-a-great-engineering-leader-9bba11bd005d" class="post-title" data-v-0320d9e7>Priorities of A Great Engineering Leader</a> <br data-v-0320d9e7>5 minutes read.<br data-v-0320d9e7><br data-v-0320d9e7>
                  Roni Poyas with a great post, covering the fundamentals of engineering leadership. I loved Roni's "Collection Of Potential Leader Success Traits" and think it can be a great practice to write your own view from different perspectives (team, stakeholders, yourself).
                  <br data-v-0320d9e7><br data-v-0320d9e7><b data-v-0320d9e7>Read</b> it later via
                  <a href="https://getpocket.com/save?url=https://medium.com/@rrpinc/priorities-of-a-great-engineering-leader-9bba11bd005d&title=Priorities%20of%20A%20Great%20Engineering%20Leader" target="_blank" data-v-7f52ad97 data-v-0320d9e7>Pocket</a>
                  or
                  <a href="http://www.instapaper.com/hello2?url=https://medium.com/@rrpinc/priorities-of-a-great-engineering-leader-9bba11bd005d&title=Priorities%20of%20A%20Great%20Engineering%20Leader" target="_blank" data-v-763e09c6 data-v-0320d9e7>Instapaper</a>. <br data-v-0320d9e7><b data-v-0320d9e7>
                    Share</b>
                  it via
                  <a href="http://twitter.com/share?text=Roni%20Poyas%20with%20a%20great%20post,%20covering%20the%20fundamentals%20of%20engineering%20leadership.%20I%20loved%20Roni"s%20%22Collection%20Of%20Potential%20Leader%20Success%20Traits%22%20and%20think%20it%20can%20be%20a%20great%20practice%20to%20write%20your%20own%20view%20from%20different%20perspectives%20(team,%20stakeholders,%20yourself).&url=https://medium.com/@rrpinc/priorities-of-a-great-engineering-leader-9bba11bd005d&via=orenellenbogen" target="_blank" data-v-727fa118 data-v-0320d9e7>Twitter</a>
                  or
                  <a href="mailto:?subject=Priorities%20of%20A%20Great%20Engineering%20Leader&body=Great post: https://medium.com/@rrpinc/priorities-of-a-great-engineering-leader-9bba11bd005d Found it via http://softwareleadweekly.com/" target="_blank" data-v-508ac71a data-v-0320d9e7>email</a>.
                  <br data-v-0320d9e7><br data-v-0320d9e7><br data-v-0320d9e7></div><div data-v-0320d9e7><a href="https://dennisnerush.medium.com/the-myth-of-the-first-90-days-bcd593c778fa" title="https://dennisnerush.medium.com/the-myth-of-the-first-90-days-bcd593c778fa" data-url="https://dennisnerush.medium.com/the-myth-of-the-first-90-days-bcd593c778fa" class="post-title" data-v-0320d9e7>The Myth of the First 90 Days</a> <br data-v-0320d9e7>5 minutes read.<br data-v-0320d9e7><br data-v-0320d9e7>
                  How quickly should you start shifting the team's operational cadence and strategy? Mapping out the goals and purpose of the team, where it should focus, and where it should expand (future opportunities) is what you should start with. Creating momentum in the wrong direction might feel good, but it's not sustainable or valuable. You have many ways to influence. Figure out which unique strength you bring to the table that the team needs now.
                  <br data-v-0320d9e7><br data-v-0320d9e7><b data-v-0320d9e7>Read</b> it later via
                  <a href="https://getpocket.com/save?url=https://dennisnerush.medium.com/the-myth-of-the-first-90-days-bcd593c778fa&title=The%20Myth%20of%20the%20First%2090%20Days" target="_blank" data-v-7f52ad97 data-v-0320d9e7>Pocket</a>
                  or
                  <a href="http://www.instapaper.com/hello2?url=https://dennisnerush.medium.com/the-myth-of-the-first-90-days-bcd593c778fa&title=The%20Myth%20of%20the%20First%2090%20Days" target="_blank" data-v-763e09c6 data-v-0320d9e7>Instapaper</a>. <br data-v-0320d9e7><b data-v-0320d9e7>
                    Share</b>
                  it via
                  <a href="http://twitter.com/share?text=How%20quickly%20should%20you%20start%20shifting%20the%20team"s%20operational%20cadence%20and%20strategy?%20Mapping%20out%20the%20goals%20and%20purpose%20of%20the%20team,%20where%20it%20should%20focus,%20and%20where%20it%20should%20expand%20(future%20opportunities)%20is%20what%20you%20should%20start%20with.%20Creating%20momentum%20in%20the%20wrong%20direction%20might%20feel%20good,%20but%20it"s%20not%20sustainable%20or%20valuable.%20You%20have%20many%20ways%20to%20influence.%20Figure%20out%20which%20unique%20strength%20you%20bring%20to%20the%20table%20that%20the%20team%20needs%20now.&url=https://dennisnerush.medium.com/the-myth-of-the-first-90-days-bcd593c778fa&via=orenellenbogen" target="_blank" data-v-727fa118 data-v-0320d9e7>Twitter</a>
                  or
                  <a href="mailto:?subject=The%20Myth%20of%20the%20First%2090%20Days&body=Great post: https://dennisnerush.medium.com/the-myth-of-the-first-90-days-bcd593c778fa Found it via http://softwareleadweekly.com/" target="_blank" data-v-508ac71a data-v-0320d9e7>email</a>.
                  <br data-v-0320d9e7><br data-v-0320d9e7><br data-v-0320d9e7></div></div></div>
        """

        # Mock the response object
        mock_response = MagicMock()
        mock_response.content = example_html
        mock_get.return_value = mock_response

        # Create an instance of ExtractArticles
        extract_articles = ExtractArticles(id="Extract Articles")

        # Mock the send method to capture the output
        extract_articles.send = MagicMock()

        # Create a mock Issue object
        mock_issue = Issue(num=613, url="http://example.com", date=date(2024, 8, 23), item_of=(0, 1))

        # Call the process method with the mock Issue
        extract_articles.process(mock_issue)

        # Check that the send method was called the correct number of times
        self.assertEqual(8, extract_articles.send.call_count)

        # Check the arguments of the first call (This Week"s Favorite)
        first_call_args = extract_articles.send.call_args_list[0][0]
        self.assertEqual("article", first_call_args[0])
        self.assertIsInstance(first_call_args[1], Article)
        self.assertEqual("Demanding and Supportive", first_call_args[1].title)
        self.assertEqual("https://www.rkg.blog/demanding.php", first_call_args[1].url)
        self.assertEqual(3, first_call_args[1].reading_time)
        self.assertEqual(613, first_call_args[1].issue_num)
        self.assertEqual((0, 8), first_call_args[1].item_of)
        self.assertEqual((0, 1), first_call_args[1].parent_item_of)
        self.assertEqual(
            """"Most people think of demanding and supportive as opposite ends of a spectrum. You can either be tough or you can be nice. But the best leaders don’t choose. They are both highly demanding and highly supportive. They push you to new heights and they also have your back. What I’ve come to realize over time is that, far from being contradictory, being demanding and supportive are inextricably linked. It’s the way you are when you believe in someone more than they believe in themselves." -- Ravi Gupta wrote it so beautifully. Many of us want to be both demanding and supportive. To our family, to our friends, to our teammates, but above all and before all - to ourselves.""",
            first_call_args[1].summary,
        )

        # Check the arguments of the second call (Culture - first article)
        second_call_args = extract_articles.send.call_args_list[1][0]
        self.assertEqual("article", second_call_args[0])
        self.assertIsInstance(second_call_args[1], Article)
        self.assertEqual('"Did You Finish Writing That PRD?"', second_call_args[1].title)
        self.assertEqual("https://x.com/carlvellotti/status/1821584562817736935", second_call_args[1].url)
        self.assertEqual(1, second_call_args[1].reading_time)
        self.assertEqual(613, second_call_args[1].issue_num)
        self.assertEqual((1, 8), second_call_args[1].item_of)
        self.assertEqual((0, 1), second_call_args[1].parent_item_of)
        self.assertEqual(
            "My humble effort to help you start the weekend with a smile on your face.", second_call_args[1].summary
        )

        # Check the third article (Culture - second article)
        third_call_args = extract_articles.send.call_args_list[2][0]
        self.assertEqual("article", third_call_args[0])
        self.assertIsInstance(third_call_args[1], Article)
        self.assertEqual("The Map Is Not the Territory", third_call_args[1].title)
        self.assertEqual("https://maruz.medium.com/the-map-is-not-the-territory-6b8bb6d86973", third_call_args[1].url)
        self.assertEqual(9, third_call_args[1].reading_time)
        self.assertEqual(613, third_call_args[1].issue_num)
        self.assertEqual((2, 8), third_call_args[1].item_of)
        self.assertEqual((0, 1), third_call_args[1].parent_item_of)
        self.assertTrue(third_call_args[1].summary)

        # Check the last article (Peopleware - third article)
        last_call_args = extract_articles.send.call_args_list[-1][0]
        self.assertEqual("article", last_call_args[0])
        self.assertIsInstance(last_call_args[1], Article)
        self.assertEqual("The Myth of the First 90 Days", last_call_args[1].title)
        self.assertEqual(
            "https://dennisnerush.medium.com/the-myth-of-the-first-90-days-bcd593c778fa", last_call_args[1].url
        )
        self.assertEqual(5, last_call_args[1].reading_time)
        self.assertEqual(613, last_call_args[1].issue_num)
        self.assertEqual((7, 8), last_call_args[1].item_of)
        self.assertEqual((0, 1), last_call_args[1].parent_item_of)
        self.assertEqual(
            "How quickly should you start shifting the team's operational cadence and strategy? Mapping out the goals and purpose of the team, where it should focus, and where it should expand (future opportunities) is what you should start with. Creating momentum in the wrong direction might feel good, but it's not sustainable or valuable. You have many ways to influence. Figure out which unique strength you bring to the table that the team needs now.",
            last_call_args[1].summary,
        )

        # Check that the articles are in the correct order
        titles = [call[0][1].title for call in extract_articles.send.call_args_list]
        expected_titles = [
            "Demanding and Supportive",
            '"Did You Finish Writing That PRD?"',
            "The Map Is Not the Territory",
            "Building With Purpose: How to Explain Developers That They Are Wasting Company Money",
            "One on One Meeting Format Ideas",
            "Circle of Competence - Mental Model",
            "Priorities of A Great Engineering Leader",
            "The Myth of the First 90 Days",
        ]
        self.assertEqual(expected_titles, titles)


class TestExtractDomainFromUrl(unittest.TestCase):
    def test_valid_url(self):
        url = "https://www.example.com/path/to/page"
        expected_domain = "example.com"
        self.assertEqual(_extract_domain_from_url(url), expected_domain)

    def test_url_with_subdomain(self):
        url = "https://subdomain.example.com/path/to/page"
        expected_domain = "example.com"
        self.assertEqual(_extract_domain_from_url(url), expected_domain)

    def test_url_without_www(self):
        url = "https://example.com/path/to/page"
        expected_domain = "example.com"
        self.assertEqual(_extract_domain_from_url(url), expected_domain)

    def test_url_with_multiple_subdomains(self):
        url = "https://sub.subdomain.example.com/path/to/page"
        expected_domain = "example.com"
        self.assertEqual(_extract_domain_from_url(url), expected_domain)

    def test_url_with_different_tld(self):
        url = "https://example.co.uk/path/to/page"
        expected_domain = "co.uk"
        self.assertEqual(_extract_domain_from_url(url), expected_domain)

    def test_url_without_protocol(self):
        url = "www.example.com/path/to/page"
        expected_domain = "unknown"
        self.assertEqual(_extract_domain_from_url(url), expected_domain)

    def test_invalid_url(self):
        url = "invalid_url"
        expected_domain = "unknown"
        self.assertEqual(_extract_domain_from_url(url), expected_domain)

    def test_empty_url(self):
        url = ""
        expected_domain = "unknown"
        self.assertEqual(_extract_domain_from_url(url), expected_domain)

    def test_url_with_ip_address(self):
        url = "https://192.168.0.1/path/to/page"
        expected_domain = "unknown"
        self.assertEqual(_extract_domain_from_url(url), expected_domain)

    def test_url_with_port(self):
        url = "https://example.com:8080/path/to/page"
        expected_domain = "example.com"
        self.assertEqual(_extract_domain_from_url(url), expected_domain)


# class TestRateLimiter(unittest.TestCase):

#     def setUp(self):
#         # Reset the singleton instance before each test
#         RateLimiter._instance = None
#         self.rate_limiter = RateLimiter()
#         self.rate_limiter._timeout = 0.1  # Set a smaller timeout for testing

#     def tearDown(self):
#         # Reset the singleton instance after each test
#         RateLimiter._instance = None

#     def test_singleton(self):
#         # Ensure that RateLimiter is a singleton
#         rate_limiter1 = RateLimiter()
#         rate_limiter2 = RateLimiter()
#         self.assertIs(rate_limiter1, rate_limiter2)

#     @patch('swlwi.scrape.datetime')
#     @patch('swlwi.scrape.time.sleep', return_value=None)
#     def test_rate_limiting(self, mock_sleep, mock_datetime):
#         # Mock the current time
#         base_time = datetime(2023, 1, 1, 12, 0, 0)
#         mock_datetime.now.return_value = base_time
#         domain = "example.com"

#         # First request should not sleep
#         start_time = time.time()
#         self.rate_limiter.wait(domain)
#         end_time = time.time()
#         self.assertLess(end_time - start_time, 0.1)
#         mock_sleep.assert_not_called()

#         # Mock the time to be 0.05 seconds later
#         mock_datetime.now.return_value = base_time + timedelta(seconds=0.05)
#         start_time = time.time()
#         self.rate_limiter.wait(domain)
#         end_time = time.time()
#         self.assertLess(end_time - start_time, 0.1)
#         mock_sleep.assert_not_called()

#         # Mock the time to be 0.15 seconds later
#         mock_datetime.now.return_value = base_time + timedelta(seconds=0.15)
#         start_time = time.time()
#         self.rate_limiter.wait(domain)
#         end_time = time.time()
#         self.assertLess(end_time - start_time, 0.1)
#         mock_sleep.assert_not_called()

#         # Mock the time to be 0.2 seconds later
#         mock_datetime.now.return_value = base_time + timedelta(seconds=0.2)
#         start_time = time.time()
#         self.rate_limiter.wait(domain)
#         end_time = time.time()
#         self.assertLess(end_time - start_time, 0.1)
#         mock_sleep.assert_not_called()

#         # Mock the time to be 0.25 seconds later
#         mock_datetime.now.return_value = base_time + timedelta(seconds=0.25)
#         start_time = time.time()
#         self.rate_limiter.wait(domain)
#         end_time = time.time()
#         self.assertGreater(end_time - start_time, 0.05)
#         mock_sleep.assert_called_once()

#     @patch('swlwi.scrape.datetime')
#     @patch('swlwi.scrape.time.sleep', return_value=None)
#     def test_rate_limiting_multiple_domains(self, mock_sleep, mock_datetime):
#         # Mock the current time
#         base_time = datetime(2023, 1, 1, 12, 0, 0)
#         mock_datetime.now.return_value = base_time
#         domain1 = "example.com"
#         domain2 = "test.com"

#         # First request for domain1 should not sleep
#         start_time = time.time()
#         self.rate_limiter.wait(domain1)
#         end_time = time.time()
#         self.assertLess(end_time - start_time, 0.1)
#         mock_sleep.assert_not_called()

#         # First request for domain2 should not sleep
#         start_time = time.time()
#         self.rate_limiter.wait(domain2)
#         end_time = time.time()
#         self.assertLess(end_time - start_time, 0.1)
#         mock_sleep.assert_not_called()

#         # Mock the time to be 0.05 seconds later
#         mock_datetime.now.return_value = base_time + timedelta(seconds=0.05)
#         start_time = time.time()
#         self.rate_limiter.wait(domain1)
#         end_time = time.time()
#         self.assertLess(end_time - start_time, 0.1)
#         mock_sleep.assert_not_called()

#         # Mock the time to be 0.15 seconds later
#         mock_datetime.now.return_value = base_time + timedelta(seconds=0.15)
#         start_time = time.time()
#         self.rate_limiter.wait(domain2)
#         end_time = time.time()
#         self.assertLess(end_time - start_time, 0.1)
#         mock_sleep.assert_not_called()

#         # Mock the time to be 0.2 seconds later
#         mock_datetime.now.return_value = base_time + timedelta(seconds=0.2)
#         start_time = time.time()
#         self.rate_limiter.wait(domain1)
#         end_time = time.time()
#         self.assertLess(end_time - start_time, 0.1)
#         mock_sleep.assert_not_called()

#         # Mock the time to be 0.25 seconds later
#         mock_datetime.now.return_value = base_time + timedelta(seconds=0.25)
#         start_time = time.time()
#         self.rate_limiter.wait(domain2)
#         end_time = time.time()
#         self.assertGreater(end_time - start_time, 0.05)
#         mock_sleep.assert_called_once()


class TestFetchArticle(unittest.TestCase):
    @patch("requests.get")
    def test_fetch_article(self, mock_get):
        example_html = """<h1>Some Article</h1>
<div class="post-content">
    <p>Some text</p>
    <p>Some more text</p>
</div>"""

        # Mock the response object
        mock_response = MagicMock()
        mock_response.text = example_html
        mock_response.content = example_html.encode()
        mock_response.encoding = "utf-8"
        mock_get.return_value = mock_response

        # Create an instance of FetchArticle
        fetch_article = FetchArticle(id="Fetch Article")

        # Create a mock Article object
        mock_article = Article(title="Some Article", url="http://example.com")

        # Call the process method with the mock Article
        actual = fetch_article.process(mock_article)

        article = actual.get("complete")

        if article is None:
            self.fail("No article found in the result")

        self.assertIsInstance(article, Article)

        self.assertEqual("Some Article", article.title)
        self.assertEqual("http://example.com", article.url)
        self.assertEqual(example_html.encode(), article.html)

    @patch("requests.get")
    def test_fetch_article_require_javascript(self, mock_get):
        example_html = """<h1>Error</h1>

        <p>
        Enable JavaScript and cookies to view this page.
        </p>"""

        # Mock the response object
        mock_response = MagicMock()
        mock_response.text = example_html
        mock_response.content = example_html.encode()
        mock_get.return_value = mock_response

        # Create an instance of FetchArticle
        fetch_article = FetchArticle(id="Fetch Article")

        # Create a mock Article object
        mock_article = Article(title="Some Article", url="http://example.com")

        # Call the process method with the mock Article
        result = fetch_article.process(mock_article)

        need_js = result.get("needs_javascript")
        complete = result.get("complete")

        if need_js is None or complete is not None:
            print(result)
            self.fail("Expected 'needs_javascript' key in the result")

        self.assertEqual(mock_article, need_js)


class TestExtractArticleContent(unittest.TestCase):
    def test_extract_article_content(self):
        example_html = """<h1>Some Article</h1>
<div class="post-content">
    <p>Some text</p>
    <p>Some more text</p>
</div>"""
        expected_markdown = """# Some Article

Some text

Some more text"""

        mock_article = Article(title="Some Article", url="http://example.com", html=example_html.encode())

        extract_article_content = ExtractArticleContent(id="Extract Article Content")

        result = extract_article_content.process(mock_article)

        article = result.get("article")
        if article is None:
            self.fail("No article found in the result")

        self.assertIsInstance(article, Article)
        self.assertEqual(expected_markdown, article.markdown)


class TestSaveArticle(unittest.TestCase):
    @patch("builtins.open", new_callable=mock_open)
    @patch("os.makedirs")
    def test_save_article(self, mock_makedirs, mock_open):
        # Create an instance of SaveArticle
        save_article = SaveArticle(id="Save Article")

        # Create a mock Article object
        mock_article = Article(
            title="Some Article",
            url="http://example.com",
            summary="Article summary",
            markdown="Some text",
            reading_time=3,
            issue_num=1,
            item_of=(6, 8),
        )
        test_path = "/tmp/articles"
        expected_path = "/tmp/articles/issue-1/article-6.md"
        expected_header = """# Some Article

Source: [http://example.com](http://example.com)
Reading time: 3 minutes

Article summary

---

"""

        # Call the process method with the mock Article
        save_article.process(article=mock_article, path=test_path)

        # Check that the file was opened with the correct arguments
        mock_open.assert_called_once_with(expected_path, "w")
        mock_open().write.assert_called_once_with(expected_header + "Some text")


if __name__ == "__main__":
    unittest.main()
